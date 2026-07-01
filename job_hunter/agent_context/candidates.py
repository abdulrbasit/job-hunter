"""Candidate queue building from DB."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

from job_hunter.agent_context._types import (
    DEFAULT_CANDIDATE_SCOPE,
    MAX_SNIPPET_CHARS,
)
from job_hunter.agent_context._utils import (
    _clip,
    _read_json_or_yaml,
    _root,
)
from job_hunter.pipeline.enrichment import classify_jd_snippet
from job_hunter.sources._policy import normalize_company_name
from job_hunter.sources.search_providers import canonicalize_url

# ---------------------------------------------------------------------------
# Legacy snapshot-file helpers (kept for tailor --links flow and --from-snapshot)
# ---------------------------------------------------------------------------


def _candidate_files(root: Path, *, today_only: bool = False, source: Path | None = None) -> list[Path]:
    if source:
        return [source]
    candidate_dir = root / "outputs" / "candidates"
    files: list[Path] = []
    for pattern in ("*_candidates.json", "*_candidates.yml", "*_candidates.yaml"):
        files.extend(candidate_dir.glob(pattern))
    if today_only:
        today = date.today().isoformat()
        files = [path for path in files if today in path.name]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _jobs_from_candidate_file(path: Path) -> list[dict[str, Any]]:
    data = _read_json_or_yaml(path)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    jobs = data.get("jobs", data.get("candidates", []))
    return [item for item in jobs if isinstance(item, dict)]


def _load_processed_for_root(root: Path) -> tuple[set[str], set[str]]:
    from job_hunter.db.jobs import get_processed_urls

    return get_processed_urls(root), set()


# ---------------------------------------------------------------------------
# Candidate ID (stable hash from URL)
# ---------------------------------------------------------------------------


def _title_key(job: dict[str, Any]) -> str:
    company = normalize_company_name(str(job.get("company") or ""))
    title = " ".join(str(job.get("title") or "").lower().split())
    return f"{company}::{title}"


def _candidate_id(job: dict[str, Any]) -> str:
    url = canonicalize_url(str(job.get("url") or "")) or str(job.get("url") or "")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()  # noqa: S324
    return f"cand_{digest[:12]}"


def _normalized_title(job: dict[str, Any]) -> str:
    return _title_key(job).split("::", 1)[-1]


# ---------------------------------------------------------------------------
# Main queue builder — reads from DB, falls back to snapshot files
# ---------------------------------------------------------------------------


def build_candidate_queue(
    *,
    root: Path | None = None,
    source: Path | None = None,
    latest: bool = False,
    today_only: bool = False,
    scope: str = DEFAULT_CANDIDATE_SCOPE,
    limit: int = 100,
    max_snippet_chars: int = MAX_SNIPPET_CHARS,
    run_id: str = "",
) -> dict[str, Any]:
    base = _root(root)

    # If a snapshot file is explicitly provided (tailor --links flow), use it
    if source and source.exists():
        return _build_queue_from_files(
            base,
            source=source,
            latest=latest,
            today_only=today_only,
            scope=scope,
            limit=limit,
            max_snippet_chars=max_snippet_chars,
        )

    # Primary path: read from DB
    return _build_queue_from_db(base, run_id=run_id, limit=limit, max_snippet_chars=max_snippet_chars)


def _build_queue_from_db(
    base: Path,
    *,
    run_id: str = "",
    limit: int = 100,
    max_snippet_chars: int = MAX_SNIPPET_CHARS,
) -> dict[str, Any]:
    from job_hunter.config import get_config
    from job_hunter.db.jobs import get_discovered_jobs
    from job_hunter.pipeline.stages.screening import screen_jobs_by_rules

    raw_jobs = get_discovered_jobs(base, run_id=run_id or None)
    processed_urls, _ = _load_processed_for_root(base)

    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    queued: list[dict[str, Any]] = []
    skipped_processed = 0
    skipped_duplicate = 0

    for job in raw_jobs:
        url = str(job.get("url") or "")
        title_key = _title_key(job)
        canonical = canonicalize_url(url) if url else ""
        if url and (canonical in processed_urls or url in seen_urls):
            skipped_processed += 1
            continue
        if title_key in seen_titles:
            skipped_duplicate += 1
            continue
        if len(queued) >= limit:
            break
        seen_urls.add(url)
        seen_titles.add(title_key)
        snippet = str(job.get("snippet") or job.get("jd_text") or "")
        queued.append(
            {
                "candidate_id": _candidate_id(job),
                "queue_index": len(queued) + 1,
                "title": str(job.get("title") or ""),
                "company": str(job.get("company") or ""),
                "url": url,
                "canonical_url": canonical,
                "normalized_company": normalize_company_name(str(job.get("company") or "")),
                "normalized_title": _normalized_title(job),
                "location": str(job.get("location") or ""),
                "region": str(job.get("region") or ""),
                "posted_date_text": str(job.get("posted_date_text") or ""),
                "source": str(job.get("source") or ""),
                "jd_status": classify_jd_snippet(snippet),
                "source_file": "db",
                "source_ordinal": 0,
                "snippet": _clip(snippet, max_snippet_chars),
            }
        )

    cfg = get_config("job_hunter") if base == _root() else {}
    queued, _hard_rejected = screen_jobs_by_rules(queued, cfg)

    return {
        "generated": date.today().isoformat(),
        "scope": "db",
        "source_files": [],
        "source_paths": [],
        "total_seen": len(raw_jobs),
        "skipped_processed": skipped_processed,
        "skipped_duplicate": skipped_duplicate,
        "skipped_hard_screen": len(_hard_rejected),
        "count": len(queued),
        "source_reports": [],
        "jobs": queued,
    }


def _build_queue_from_files(
    base: Path,
    *,
    source: Path | None = None,
    latest: bool = False,
    today_only: bool = False,
    scope: str = DEFAULT_CANDIDATE_SCOPE,
    limit: int = 100,
    max_snippet_chars: int = MAX_SNIPPET_CHARS,
) -> dict[str, Any]:
    """Legacy snapshot-file queue builder (used when --source is given)."""
    from job_hunter.config import get_config
    from job_hunter.pipeline.stages.screening import screen_jobs_by_rules

    resolved_today_only = today_only
    if scope == "today":
        resolved_today_only = True

    files = _candidate_files(base, today_only=resolved_today_only, source=source)
    if latest and files:
        files = files[:1]

    processed_urls, _ = _load_processed_for_root(base)
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    queued: list[dict[str, Any]] = []
    total_seen = 0
    skipped_processed = 0
    skipped_duplicate = 0
    source_reports: list[dict[str, Any]] = []

    for path in files:
        source_total = 0
        source_queued = 0
        source_skip_proc = 0
        source_skip_dup_url = 0
        source_skip_dup_title = 0
        for source_ordinal, job in enumerate(_jobs_from_candidate_file(path), start=1):
            source_total += 1
            total_seen += 1
            url = str(job.get("url") or "")
            title_key = _title_key(job)
            canonical = canonicalize_url(url) if url else ""
            if url and (canonical in processed_urls or url in seen_urls):
                if canonical in processed_urls:
                    source_skip_proc += 1
                    skipped_processed += 1
                else:
                    source_skip_dup_url += 1
                    skipped_duplicate += 1
                continue
            if title_key in seen_titles:
                source_skip_dup_title += 1
                skipped_duplicate += 1
                continue
            if len(queued) < limit:
                seen_urls.add(url)
                seen_titles.add(title_key)
                snippet = str(job.get("snippet") or job.get("description") or "")
                queued.append(
                    {
                        "candidate_id": _candidate_id(job),
                        "queue_index": len(queued) + 1,
                        "title": str(job.get("title") or ""),
                        "company": str(job.get("company") or ""),
                        "url": url,
                        "canonical_url": canonical,
                        "normalized_company": normalize_company_name(str(job.get("company") or "")),
                        "normalized_title": _normalized_title(job),
                        "location": str(job.get("location") or ""),
                        "region": str(job.get("region") or ""),
                        "posted_date_text": str(job.get("posted_date_text") or ""),
                        "source": str(job.get("source") or ""),
                        "jd_status": str(job.get("jd_status") or classify_jd_snippet(snippet)),
                        "source_file": path.name,
                        "source_ordinal": source_ordinal,
                        "snippet": _clip(snippet, max_snippet_chars),
                    }
                )
                source_queued += 1

        source_skipped = source_skip_proc + source_skip_dup_url + source_skip_dup_title
        reason = ""
        if source_total == 0:
            reason = "no_candidates"
        elif source_queued == 0:
            reason = "all_processed_or_duplicate" if source_skipped == source_total else "no_queueable_candidates"
        source_reports.append(
            {
                "file": path.name,
                "path": path.as_posix(),
                "total_seen": source_total,
                "queued": source_queued,
                "skipped_processed_url": source_skip_proc,
                "skipped_duplicate_url": source_skip_dup_url,
                "skipped_duplicate_title": source_skip_dup_title,
                "reason": reason,
            }
        )

    cfg = get_config("job_hunter") if base == _root() else {}
    queued, _hard_rejected = screen_jobs_by_rules(queued, cfg)

    return {
        "generated": date.today().isoformat(),
        "scope": "today" if resolved_today_only else "briefing-backlog",
        "source_files": [path.name for path in files],
        "source_paths": [path.as_posix() for path in files],
        "total_seen": total_seen,
        "skipped_processed": skipped_processed,
        "skipped_duplicate": skipped_duplicate,
        "skipped_hard_screen": len(_hard_rejected),
        "count": len(queued),
        "source_reports": source_reports,
        "jobs": queued,
    }


def candidate_from_queue(path: Path, index: int = 1, candidate_id: str = "") -> dict[str, Any]:
    data = _read_json_or_yaml(path)
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    if candidate_id:
        for job in jobs:
            if str(job.get("candidate_id") or "") == candidate_id:
                return job
        raise KeyError(f"candidate id {candidate_id} not found in queue")
    if index < 1 or index > len(jobs):
        raise IndexError(f"candidate index {index} outside queue size {len(jobs)}")
    return jobs[index - 1]
