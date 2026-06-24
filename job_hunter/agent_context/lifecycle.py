"""Candidate lifecycle helpers and score file validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from job_hunter.agent_context._types import (
    DEFAULT_CANDIDATE_SCOPE,
    DEFAULT_QUEUE_PATH,
    JD_LIFECYCLE_IMPORT_STATUSES,
    MAX_JD_CHARS,
)
from job_hunter.agent_context._utils import _resolve_path, _root
from job_hunter.agent_context.candidates import (
    _load_processed_for_root,
    build_candidate_queue,
    candidate_from_queue,
)
from job_hunter.agent_context.score_context import _read_job_folder
from job_hunter.pipeline.enrichment import classify_jd_snippet
from job_hunter.sources.search_providers import canonicalize_url
from job_hunter.tracking._io import _read_state, _write_state


def validate_score_file(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {"valid": False, "path": path.as_posix(), "error": str(exc)}
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return {"valid": False, "path": path.as_posix(), "error": str(exc)}
    required = {
        "score",
        "decision",
        "matched_story_ids",
        "matched",
        "gaps",
        "role_summary",
        "score_rationale",
        "recommendation",
    }
    missing = sorted(required - set(data.keys()))
    if missing:
        return {
            "valid": False,
            "path": path.as_posix(),
            "error": f"missing required keys: {', '.join(missing)}",
        }
    return {"valid": True, "path": path.as_posix(), "score": data.get("score")}


def _processed_state_path(root: Path) -> Path:
    return root / "outputs" / "state" / "discovered_urls.yml"


def _save_processed_for_root(root: Path, urls: set[str], titles: set[str]) -> None:
    path = _processed_state_path(root)
    existing = _read_state(path)
    candidate_urls = set(existing.get("candidate_urls", []) or [])
    _write_state(path, urls, candidate_urls)


def _mark_candidate_processed(root: Path, candidate: dict[str, Any]) -> dict[str, int]:
    urls, _ = _load_processed_for_root(root)
    before_urls = len(urls)
    url = canonicalize_url(str(candidate.get("url") or ""))
    if url:
        urls.add(url)
    _save_processed_for_root(root, urls, set())
    return {
        "new_urls": len(urls) - before_urls,
        "total_urls": len(urls),
    }


def _write_refreshed_queue(
    root: Path,
    queue_path: Path | str,
    *,
    today_only: bool = False,
    scope: str = DEFAULT_CANDIDATE_SCOPE,
) -> dict[str, Any]:
    output = _resolve_path(root, queue_path)
    queue = build_candidate_queue(root=root, today_only=today_only, scope=scope)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return {
        "path": output.as_posix(),
        "count": queue["count"],
        "total_seen": queue["total_seen"],
    }


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, str]:
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "title": str(candidate.get("title") or ""),
        "company": str(candidate.get("company") or ""),
        "url": str(candidate.get("url") or ""),
        "jd_status": str(candidate.get("jd_status") or ""),
    }


def candidate_lifecycle(
    *,
    root: Path | None = None,
    queue: Path | None = None,
    index: int = 1,
    candidate_id: str = "",
    job: str = "",
    terminal_reason: str = "",
    refresh_queue: Path | None = None,
    fallback_text: str = "",
    today_only: bool = False,
    scope: str = DEFAULT_CANDIDATE_SCOPE,
) -> dict[str, Any]:
    """Return or apply deterministic lifecycle actions for workflow skills.

    This helper keeps candidate/JD state handling in Python. It does not make
    judgment calls and does not fetch external pages.
    """
    base = _root(root)
    candidate: dict[str, Any] = {}
    if queue:
        candidate = candidate_from_queue(_resolve_path(base, queue), index, candidate_id=candidate_id)

    result: dict[str, Any] = {
        "component": "agent_context.candidate_lifecycle",
        "candidate": _candidate_summary(candidate) if candidate else {},
    }

    if terminal_reason:
        if not candidate:
            raise ValueError("--mark-terminal requires --queue and --index")
        result["action"] = "terminal_marked"
        result["reason"] = terminal_reason
        result["processed"] = _mark_candidate_processed(base, candidate)
        if refresh_queue:
            result["refreshed_queue"] = _write_refreshed_queue(
                base,
                refresh_queue,
                today_only=today_only,
                scope=scope,
            )
        return result

    if job:
        job_context = _read_job_folder(base, job, MAX_JD_CHARS)
        meta = job_context.get("meta", {})
        fetch_status = str(meta.get("fetch_status") or "")
        result["job"] = {"slug": job, "fetch_status": fetch_status}
        if fetch_status == "fetch_failed":
            if fallback_text:
                fallback_status = classify_jd_snippet(fallback_text)
                result["fallback_text_status"] = fallback_status
                if fallback_status == "full":
                    result["action"] = "reimport_with_fallback"
                    result["reason"] = "fallback_text_is_full_jd"
                    return result
                result["action"] = "terminal_candidate"
                result["reason"] = "fallback_text_not_full_jd"
                return result
            result["action"] = "webfetch_required"
            result["reason"] = "job_fetch_failed"
            return result
        result["action"] = "full_score"
        result["reason"] = "job_imported"
        result["score_command"] = f"job-hunter agent-context score --mode full --job {job}"
        return result

    if not candidate:
        raise ValueError("lifecycle requires --queue/--index or --job")

    jd_status = str(candidate.get("jd_status") or "")
    queue_label = queue.as_posix() if queue else DEFAULT_QUEUE_PATH
    candidate_selector = f"--candidate-id {candidate_id}" if candidate_id else f"--index {index}"
    if jd_status in JD_LIFECYCLE_IMPORT_STATUSES:
        result["action"] = "import_required"
        result["reason"] = f"candidate_jd_status:{jd_status}"
        result["import_command"] = f"job-hunter import-job --queue {queue_label} {candidate_selector}"
        return result

    result["action"] = "snippet_score"
    result["reason"] = f"candidate_jd_status:{jd_status or 'unknown'}"
    result["score_command"] = (
        f"job-hunter agent-context score --mode snippet --queue {queue_label} {candidate_selector}"
    )
    return result
