"""Candidate batch building and screening helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from job_hunter.agent_context._utils import _root
from job_hunter.agent_context.candidates import _job_hunter_config_for, _title_key
from job_hunter.constants import DEFAULT_BATCH_SIZE
from job_hunter.sources.policy import JobPolicy


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
    """Return title+company keys for jobs currently in the pipeline.

    Reads outputs/jobs/*/meta.json (active job folders) and applications.yml
    (active-status entries only). README.md is intentionally excluded — it is a
    display artifact and can be stale after deletions.
    """
    from job_hunter.tracking.applications import ACTIVE_STATUSES, load_applications

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

    for app in load_applications(root).get("applications", []):
        if str(app.get("status") or "") in ACTIVE_STATUSES:
            key = _title_key({"company": app.get("company", ""), "title": app.get("title", "")})
            if key != "::":
                keys.add(key)

    return keys


def _region_config(search_config: dict[str, Any], region: str) -> dict[str, Any]:
    regions = search_config.get("regions", {}) or {}
    config = regions.get(region, {})
    return config if isinstance(config, dict) else {}


def screen_candidate_batch(
    batch: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    base = _root(root)
    search_config = _job_hunter_config_for(base)
    policy = JobPolicy(search_config)
    title_filters = search_config.get("job_titles", []) or []
    applied_keys = _applied_title_keys(base)
    excluded_industries = [term.lower() for term in policy.excluded_industries]

    retained: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in batch.get("jobs", []):
        reasons: list[str] = []
        title = str(candidate.get("title") or "")
        snippet = str(candidate.get("snippet") or "")
        region = str(candidate.get("region") or "")
        content_reason = policy.rejection_reason(candidate, title_filters)
        if content_reason:
            reasons.append(content_reason)
        region_config = _region_config(search_config, region)
        if policy.has_incompatible_location_metadata(candidate, region_config):
            reasons.append("incompatible_location_metadata")
        if "incompatible_location_metadata" not in reasons and policy.has_wrong_location(candidate, region_config):
            reasons.append("wrong_location")
        if policy.excluded_by_search_lang(title, snippet, region_config.get("search_lang", "en")):
            reasons.append("excluded_by_search_lang")
        if policy.is_location_restricted(title, snippet):
            reasons.append("location_restricted")
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
            row["judgment_signals"] = {
                "industry_terms": [term for term in excluded_industries if term in snippet.lower()],
            }
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
