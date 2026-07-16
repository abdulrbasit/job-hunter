"""Fail-fast rejection of pre-cutoff config keys.

Every key here was removed from job_hunter.yml's schema. Loading a workspace
that still has one raises immediately with migration guidance, instead of the
key being silently ignored.
"""

from __future__ import annotations

from typing import Any

_TOP_LEVEL_REMOVED = ("about_me", "sources", "secrets", "tailoring", "cover_letter", "exclusions")
_EXCLUSIONS_REMOVED = ("senior_flags", "stale_indicators", "url_patterns", "language_indicators")
_FILTERS_REMOVED = ("excluded_languages",)


def reject_removed_user_config(data: dict[str, Any]) -> None:
    """Fail fast when a workspace still uses pre-cutoff config keys."""
    found = [key for key in _TOP_LEVEL_REMOVED if key in data]

    exclusions = data.get("exclusions", {}) or {}
    for key in _EXCLUSIONS_REMOVED:
        if key in exclusions:
            found.append(f"exclusions.{key}")

    filters = data.get("filters", {}) or {}
    for key in _FILTERS_REMOVED:
        if key in filters:
            found.append(f"filters.{key}")

    scoring = data.get("scoring", {}) or {}
    if "prompt_context" in scoring:
        found.append("scoring.prompt_context")

    linkedin = data.get("linkedin", {}) or {}
    rich_linkedin_keys = sorted(set(linkedin) - {"enabled"})
    found.extend(f"linkedin.{key}" for key in rich_linkedin_keys)

    if found:
        joined = ", ".join(found)
        guidance = (
            " Run `job-hunter doctor` or `job-hunter update` to migrate exclusions into filters."
            if "exclusions" in found
            else " Use filters.hunt_languages as the allowlist."
            if "filters.excluded_languages" in found
            else " Update to the v1 compact config shape."
        )
        raise ValueError(f"Removed job_hunter.yml key(s): {joined}.{guidance}")
