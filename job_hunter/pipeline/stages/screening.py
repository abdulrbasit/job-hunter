"""Objective screening shared by agent and LLM API modes."""

from __future__ import annotations

from typing import Any

from job_hunter.core.utils import has_excluded_title_term
from job_hunter.sources.policy import JobPolicy


def _requires_excluded_language(title_lower: str, excluded_langs: list[str]) -> bool:
    for lang in excluded_langs:
        if f"{lang} speaking" in title_lower or f"fluent in {lang}" in title_lower or f"{lang} speaker" in title_lower:
            return True
    return False


def _screen_job(
    job: dict[str, Any],
    policy: JobPolicy,
    regions: dict[str, Any],
    industries: list[str],
    title_filters: list[str],
) -> tuple[str, list[str]]:
    title = str(job.get("title") or "")
    snippet = str(job.get("snippet") or "")
    snippet_lower = snippet.lower()

    reason = policy.rejection_reason(job, title_filters)
    if not reason and has_excluded_title_term(title, policy.excluded_title_terms):
        reason = "excluded_title"
    if not reason and _requires_excluded_language(title.lower(), policy.excluded_languages):
        reason = "requires_language"

    region = str(job.get("region") or "")
    region_config = regions.get(region, {}) if isinstance(regions, dict) else {}

    if not reason and policy.has_incompatible_location_metadata(job, region_config):
        reason = "incompatible_location_metadata"
    if not reason and policy.has_wrong_location(job, region_config):
        reason = "wrong_location"
    if not reason and not region_config and policy.has_incompatible_location_for_global_feed(job):
        # Jobs with no per-region context (e.g. company-hunt career-page scrapes,
        # which don't tag a "region" key) skip has_incompatible_location_metadata/
        # has_wrong_location above entirely, since both no-op on an empty
        # region_config — this is the same fallback orchestrator.py already applies
        # for global-feed sources with no region context.
        reason = "incompatible_location_metadata"
    if not reason and policy.is_location_restricted(title, snippet):
        reason = "location_restricted"

    if not reason:
        search_lang = (region_config.get("search_lang") or "en") if isinstance(region_config, dict) else "en"
        if policy.excluded_by_search_lang(title, snippet, search_lang):
            reason = "excluded_by_search_lang"

    if not reason and policy.is_excluded_industry(snippet_lower):
        reason = "excluded_industry"

    signals = [] if reason else [term for term in industries if term in snippet_lower]
    return reason, signals


def screen_jobs_by_rules(
    jobs: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove objective failures and preserve semantic questions as signals."""
    policy = JobPolicy(config)
    regions = config.get("regions", {}) or {}
    industries = [str(term).lower() for term in policy.excluded_industries]
    title_filters = [str(term) for term in config.get("job_titles", []) or []]
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for job in jobs:
        reason, signals = _screen_job(job, policy, regions, industries, title_filters)
        if reason:
            rejected.append({**job, "_rejection_reason": reason})
        else:
            kept.append({**job, **({"_judgment_signals": {"industry_terms": signals}} if signals else {})})

    return kept, rejected
