"""Merges the bundled company catalog with a workspace's custom career_pages.yml entries."""

from __future__ import annotations

from typing import Any

from job_hunter.catalog.loader import CompanyEntry, load_companies
from job_hunter.config.reference_data import load_filters
from job_hunter.locations import canonicalize_runtime_location, enabled_locations, location_matches_any
from job_hunter.models import Location


def _normalize_url(url: str) -> str:
    return url.rstrip("/").lower()


def _excluded_industry_ids(user_terms: list[str]) -> set[str]:
    """Expand excluded-industry values to known IDs via id/label/alias match.

    Unknown strings (no matching industry) simply expand to nothing here — they
    never matched catalog companies anyway, since companies are tagged by ID.
    """
    industries = load_filters().industries
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


def _is_eligible(
    company: CompanyEntry,
    allowed_locations: list[Location],
    excluded_industry_ids: set[str],
    enabled_ids: set[str],
) -> bool:
    if company.id not in enabled_ids:
        return False
    if excluded_industry_ids and set(company.industry_ids) & excluded_industry_ids:
        return False
    return company_matches_enabled_locations(company, allowed_locations)


def company_matches_enabled_locations(company: CompanyEntry, allowed_locations: list[Location]) -> bool:
    return location_matches_any(company.location_evidence(), allowed_locations)


def effective_companies(job_hunter_config: dict[str, Any], career_pages_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Enabled bundled catalog companies + enabled custom companies.

    Catalog companies are opt-in: a company only runs once its id is in
    `catalog.enabled_company_ids` (per-company or bulk "enable this sector" in the
    Shared Catalog UI). Custom `career_pages.yml` entries stay enabled by default —
    they're the user's own additions. A custom entry whose career_url matches a
    bundled company wins — the bundled entry is skipped rather than duplicated.
    """
    catalog_settings = career_pages_data.get("catalog") or {}
    enabled_ids = {str(company_id) for company_id in catalog_settings.get("enabled_company_ids", []) or []}

    custom_companies = [c for c in career_pages_data.get("companies", []) or [] if isinstance(c, dict)]
    custom_urls = {_normalize_url(str(c.get("career_url") or "")) for c in custom_companies}

    from job_hunter.config.filter_registry import FilterRegistry

    industry_filter = FilterRegistry.from_config(job_hunter_config).file("excluded_industries")
    excluded_industry_ids = _excluded_industry_ids(industry_filter.values if industry_filter else [])
    allowed_locations = enabled_locations(job_hunter_config)

    effective: list[dict[str, Any]] = []
    if enabled_ids:
        for company in load_companies():
            if not _is_eligible(company, allowed_locations, excluded_industry_ids, enabled_ids):
                continue
            if _normalize_url(company.career_url) in custom_urls:
                continue
            effective.append(
                {
                    "id": company.id,
                    "name": company.name,
                    "career_url": company.career_url,
                    "location": ", ".join(company.city_tags),
                    "source": "catalog",
                }
            )

    for custom in custom_companies:
        if custom.get("enabled", True) is False:
            continue
        custom_locations = canonicalize_runtime_location(str(custom.get("location") or ""))
        if not location_matches_any(custom_locations, allowed_locations):
            continue
        effective.append(
            {
                "name": custom.get("name"),
                "career_url": custom.get("career_url"),
                "location": custom.get("location") or "",
                "source": "custom",
            }
        )

    return effective
