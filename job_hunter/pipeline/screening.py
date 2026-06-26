"""Objective screening shared by agent and LLM API modes."""

from __future__ import annotations

from typing import Any

from job_hunter.core.utils import title_matches
from job_hunter.sources._policy import JobPolicy


def hard_screen_jobs(
    jobs: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove objective failures and preserve semantic questions as signals."""
    policy = JobPolicy(config)
    regions = config.get("regions", {}) or {}
    industries = [str(term).lower() for term in policy.excluded_industries]
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for job in jobs:
        title = str(job.get("title") or "")
        reason = policy.rejection_reason(job, [])
        if not reason and not title_matches(title, [], policy.excluded_title_terms):
            reason = "excluded_title"
        region = str(job.get("region") or "")
        region_config = regions.get(region, {}) if isinstance(regions, dict) else {}
        if not reason and policy.has_wrong_location(job, region_config):
            reason = "wrong_location"
        if not reason and policy.is_location_restricted(title, str(job.get("snippet") or "")):
            reason = "location_restricted"
        if reason:
            rejected.append({**job, "_rejection_reason": reason})
            continue

        snippet = str(job.get("snippet") or "").lower()
        signals = [term for term in industries if term in snippet]
        kept.append({**job, **({"_judgment_signals": {"industry_terms": signals}} if signals else {})})

    return kept, rejected
