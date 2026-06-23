"""Candidate batch building and screening helpers."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from job_hunter.agent_context._utils import _read_yaml, _root
from job_hunter.agent_context.candidates import _title_key
from job_hunter.config import get_config
from job_hunter.constants import DEFAULT_BATCH_SIZE
from job_hunter.sources._policy import JobPolicy


def build_candidate_batch(
    queue: dict[str, Any],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    batch_number: int = 1,
) -> dict[str, Any]:
    jobs = queue.get("jobs", []) if isinstance(queue, dict) else []
    selected = jobs[:batch_size]
    return {
        "generated": date.today().isoformat(),
        "batch_number": batch_number,
        "batch_size": batch_size,
        "source_queue_count": len(jobs),
        "count": len(selected),
        "jobs": selected,
    }


def _applied_title_keys(root: Path) -> set[str]:
    keys: set[str] = set()
    jobs_dir = root / "outputs" / "jobs"
    if jobs_dir.exists():
        for meta_path in jobs_dir.glob("*/meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            key = _title_key(meta)
            if key != "::":
                keys.add(key)

    readme_path = root / "README.md"
    if readme_path.exists():
        try:
            readme = readme_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            readme = readme_path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"\[([^\]]+?) @ ([^\]]+?)\]\(https?://", readme):
            title, company = match.group(1), match.group(2)
            keys.add(_title_key({"company": company, "title": title}))
    return keys


def _region_config(search_config: dict[str, Any], region: str) -> dict[str, Any]:
    regions = search_config.get("regions", {}) or {}
    cfg = regions.get(region, {})
    return cfg if isinstance(cfg, dict) else {}


def screen_candidate_batch(
    batch: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    base = _root(root)
    search_config = get_config("job_hunter") if base == _root() else _read_yaml(base / "config" / "job_hunter.yml")
    policy = JobPolicy(search_config)
    title_filters = search_config.get("job_titles", []) or []
    applied_keys = _applied_title_keys(base)

    retained: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in batch.get("jobs", []):
        reasons: list[str] = []
        title = str(candidate.get("title") or "")
        snippet = str(candidate.get("snippet") or "")
        region = str(candidate.get("region") or "")
        if not policy.accepts_job_content(candidate, title_filters):
            if policy.is_excluded_company(str(candidate.get("company") or "")):
                reasons.append("excluded_company")
            if policy.is_excluded_language(title, snippet):
                reasons.append("excluded_language")
            if any(term.lower() in title.lower() for term in policy.excluded_title_terms):
                reasons.append("excluded_title")
            if policy.is_excluded_industry(snippet):
                reasons.append("excluded_industry")
            if not reasons:
                reasons.append("title_not_matched")
        if policy.has_wrong_location(candidate, _region_config(search_config, region)):
            reasons.append("wrong_location")
        if policy.is_stale_posting(title, snippet):
            reasons.append("stale_posting")
        if _title_key(candidate) in applied_keys:
            reasons.append("duplicate_application")

        row = {
            "candidate_id": candidate.get("candidate_id"),
            "queue_index": candidate.get("queue_index"),
            "title": candidate.get("title"),
            "company": candidate.get("company"),
            "url": candidate.get("url"),
            "reasons": reasons,
        }
        if reasons:
            skipped.append(row)
        else:
            retained.append(row)

    return {
        "generated": date.today().isoformat(),
        "batch_number": batch.get("batch_number", 1),
        "batch_size": batch.get("batch_size", DEFAULT_BATCH_SIZE),
        "loaded": len(batch.get("jobs", [])),
        "retained_count": len(retained),
        "skipped_count": len(skipped),
        "retained": retained,
        "skipped": skipped,
    }
