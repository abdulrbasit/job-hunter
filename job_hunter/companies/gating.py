"""Region + industry-exclusion gating for company selection (hunt candidates, ATS slugs)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from job_hunter.companies import store
from job_hunter.config.reference_data import startups_enabled
from job_hunter.filters.catalog import load_filter_catalog
from job_hunter.locations import city_by_id, enabled_locations
from job_hunter.models import LocationScope


def enabled_countries(config: dict[str, Any]) -> list[str] | None:
    """Countries a company must be in to be eligible. None = every country (remote_global)."""
    locations = enabled_locations(config)
    if any(location.scope == LocationScope.REMOTE_GLOBAL for location in locations):
        return None
    return sorted({location.country for location in locations if location.country})


def excluded_industry_ids(user_terms: list[str]) -> set[str]:
    """Expand excluded-industry values (id, label, or alias) to known taxonomy IDs."""
    industries = load_filter_catalog().industries
    excluded: set[str] = set()
    for term in user_terms:
        needle = str(term).strip().lower()
        if not needle:
            continue
        for industry in industries:
            names = {industry.id.lower(), industry.label.lower(), *(a.lower() for a in industry.aliases)}
            if needle in names:
                excluded.add(industry.id)
    return excluded


def _location_text(row: dict[str, Any]) -> str:
    if row.get("city"):
        city = city_by_id(row["country"], row["city"])
        if city is not None:
            return city.name
    return row["country"]


def hunt_candidates(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Enabled companies eligible for a company hunt, as career-page-scraper dicts."""
    from job_hunter.config.service import read_company_targets
    from job_hunter.filters import filter_values

    store.ensure_seeded(root)
    store.sync_user_targets(root, read_company_targets(root)["data"]["targets"])

    excluded = excluded_industry_ids(filter_values(config, "excluded_industries"))
    rows = store.candidate_companies(
        root,
        countries=enabled_countries(config),
        excluded_industries=excluded,
        include_startups=startups_enabled(config),
        startup_cap=100,
    )
    return [
        {
            "name": row["name"],
            "career_url": row["url"],
            "location": _location_text(row),
            "source": row["source"],
            "company_type": row["company_type"],
            "funding_stage": row["funding_stage"],
        }
        for row in rows
    ]
