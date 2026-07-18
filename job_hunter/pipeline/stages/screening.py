"""Objective screening shared by agent and LLM API modes."""

from __future__ import annotations

from typing import Any

from job_hunter.core.utils import has_excluded_title_term
from job_hunter.locations import enabled_locations, job_matches_enabled_locations
from job_hunter.sources.policy import JobPolicy, format_experience_reason_detail


def _screen_experience_and_language(policy: JobPolicy, title: str, description: str) -> tuple[str, dict[str, Any], str]:
    """The two content-based deterministic gates, both fail-open on ambiguous reads."""
    judgment_signals: dict[str, Any] = {}

    excluded, exp_detail, experience_unknown = policy.experience_screen(title, description)
    if excluded:
        detail = format_experience_reason_detail(exp_detail) if exp_detail else ""
        return "experience_out_of_range", judgment_signals, detail
    if experience_unknown:
        judgment_signals["experience_unknown"] = True

    excluded, _detected_code, language_uncertain = policy.language_screen(title, description)
    if excluded:
        return "language_not_hunted", judgment_signals, ""
    if language_uncertain:
        judgment_signals["language_uncertain"] = True

    return "", judgment_signals, ""


def _screen_job(
    job: dict[str, Any],
    policy: JobPolicy,
    regions: dict[str, Any],
    industries: list[str],
    title_filters: list[str],
    allowed_locations: list[Any] | None = None,
) -> tuple[str, dict[str, Any], str]:
    title = str(job.get("title") or "")
    snippet = str(job.get("snippet") or "")
    snippet_lower = snippet.lower()
    judgment_signals: dict[str, Any] = {}
    rejection_detail = ""

    reason = policy.rejection_reason(job, title_filters)
    if not reason and has_excluded_title_term(title, policy.excluded_title_terms):
        reason = "excluded_title"
    region = str(job.get("region") or "")
    region_config = regions.get(region, {}) if isinstance(regions, dict) else {}

    if not reason and policy.is_excluded_industry(snippet_lower):
        reason = "excluded_industry"

    if not reason and allowed_locations is not None and not job_matches_enabled_locations(job, allowed_locations):
        reason = "location_not_enabled"

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
        description = str(job.get("full_job_description") or snippet)
        reason, extra_signals, rejection_detail = _screen_experience_and_language(policy, title, description)
        judgment_signals.update(extra_signals)

    if not reason:
        signals = [term for term in industries if term in snippet_lower]
        if signals:
            judgment_signals["industry_terms"] = signals
    return reason, judgment_signals, rejection_detail


def screen_jobs_by_rules(
    jobs: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove objective failures and preserve semantic questions as signals."""
    policy = JobPolicy(config)
    regions = config.get("regions", {}) or {}
    allowed_locations = enabled_locations(config) if "regions" in config else None
    industries = [str(term).lower() for term in policy.excluded_industries]
    title_filters = [str(term) for term in config.get("job_titles", []) or []]
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for job in jobs:
        reason, judgment_signals, rejection_detail = _screen_job(
            job, policy, regions, industries, title_filters, allowed_locations
        )
        if reason:
            rejected.append(
                {
                    **job,
                    "_rejection_reason": reason,
                    **({"_rejection_detail": rejection_detail} if rejection_detail else {}),
                }
            )
            continue
        kept.append(
            {
                **job,
                **({"experience_unknown": True} if judgment_signals.get("experience_unknown") else {}),
                **({"_judgment_signals": judgment_signals} if judgment_signals else {}),
            }
        )

    return kept, rejected
