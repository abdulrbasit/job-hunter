"""Merges the bundled company catalog with a workspace's custom career_pages.yml entries."""

from __future__ import annotations

from typing import Any

from job_hunter.catalog.loader import CompanyEntry, load_companies
from job_hunter.config.reference_data import load_filters


def _normalize_url(url: str) -> str:
    return url.rstrip("/").lower()


def _enabled_country_codes(job_hunter_config: dict[str, Any]) -> set[str]:
    regions = job_hunter_config.get("regions", {}) or {}
    codes: set[str] = set()
    for region in regions.values() if isinstance(regions, dict) else []:
        if isinstance(region, dict) and region.get("enabled", True):
            country = str(region.get("country") or "").strip().upper()
            if country:
                codes.add(country)
    return codes


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
    enabled_countries: set[str],
    excluded_industry_ids: set[str],
    enabled_ids: set[str],
) -> bool:
    if company.id not in enabled_ids:
        return False
    if excluded_industry_ids and set(company.industry_ids) & excluded_industry_ids:
        return False
    if not enabled_countries:
        return True
    return bool(set(company.country_codes) & enabled_countries) or bool(
        set(company.remote_country_codes) & enabled_countries
    )


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
    enabled_countries = _enabled_country_codes(job_hunter_config)

    effective: list[dict[str, Any]] = []
    if enabled_ids:
        for company in load_companies():
            if not _is_eligible(company, enabled_countries, excluded_industry_ids, enabled_ids):
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
        effective.append(
            {
                "name": custom.get("name"),
                "career_url": custom.get("career_url"),
                "location": custom.get("location") or "",
                "source": "custom",
            }
        )

    return effective
