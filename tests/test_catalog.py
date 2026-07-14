"""Tests for job_hunter/catalog/ — the bundled company catalog and its merge with career_pages.yml."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from job_hunter.catalog import effective_companies, load_companies
from job_hunter.catalog.loader import _CompaniesFile

# ---------------------------------------------------------------------------
# Catalog loading — count, uniqueness, URL shape, metadata
# ---------------------------------------------------------------------------


def test_catalog_loads_at_least_one_company() -> None:
    companies = load_companies()

    assert len(companies) >= 1


def test_catalog_company_ids_are_unique() -> None:
    ids = [c.id for c in load_companies()]

    assert len(ids) == len(set(ids))


def test_catalog_career_urls_are_unique_https() -> None:
    companies = load_companies()
    urls = [c.career_url.rstrip("/").lower() for c in companies]

    assert len(urls) == len(set(urls))
    assert all(url.startswith("https://") for url in urls)


def test_catalog_companies_have_country_and_verified_date() -> None:
    """industry_ids may be empty — companies migrated in bulk without a reliable
    sector classification land in the Shared Catalog UI's "Uncategorized" bucket
    rather than have a guessed/fabricated industry."""
    for company in load_companies():
        assert company.country_codes
        assert company.verified_at


def test_catalog_rejects_unknown_country_code() -> None:
    bad = {
        "version": 1,
        "count": 1,
        "companies": [
            {
                "id": "acme",
                "name": "Acme",
                "career_url": "https://acme.example/careers",
                "country_codes": ["ZZ"],
                "industry_ids": ["software_it"],
                "verified_at": "2026-01-01",
            }
        ],
    }
    with pytest.raises(ValidationError):
        _CompaniesFile.model_validate(bad)


def test_catalog_rejects_unknown_industry_id() -> None:
    bad = {
        "version": 1,
        "count": 1,
        "companies": [
            {
                "id": "acme",
                "name": "Acme",
                "career_url": "https://acme.example/careers",
                "country_codes": ["US"],
                "industry_ids": ["not-a-real-industry"],
                "verified_at": "2026-01-01",
            }
        ],
    }
    with pytest.raises(ValidationError):
        _CompaniesFile.model_validate(bad)


def test_catalog_rejects_duplicate_company_id() -> None:
    entry = {
        "id": "acme",
        "name": "Acme",
        "career_url": "https://acme.example/careers",
        "country_codes": ["US"],
        "industry_ids": ["software_it"],
        "verified_at": "2026-01-01",
    }
    bad = {"version": 1, "count": 2, "companies": [entry, {**entry, "career_url": "https://acme.example/jobs"}]}
    with pytest.raises(ValidationError):
        _CompaniesFile.model_validate(bad)


def test_catalog_rejects_non_https_career_url() -> None:
    bad = {
        "id": "acme",
        "name": "Acme",
        "career_url": "http://acme.example/careers",
        "country_codes": ["US"],
        "industry_ids": ["software_it"],
        "verified_at": "2026-01-01",
    }
    with pytest.raises(ValidationError):
        _CompaniesFile.model_validate({"version": 1, "count": 1, "companies": [bad]})


# ---------------------------------------------------------------------------
# effective_companies — opt-in allowlist, region selection, overrides, dedupe,
# industry exclusion
# ---------------------------------------------------------------------------

_DE_CONFIG = {"regions": {"primary": {"enabled": True, "country": "DE"}}, "exclusions": {}}
_NO_REGION_CONFIG: dict = {"regions": {}, "exclusions": {}}
_SAP_SIEMENS_GOOGLE = {"catalog": {"enabled_company_ids": ["sap", "siemens", "google"]}}


def test_effective_companies_defaults_to_no_catalog_companies() -> None:
    """Shared catalog companies are opt-in — an empty (or absent) allowlist means none run."""
    result = effective_companies(_DE_CONFIG, {"companies": []})

    assert not [c for c in result if c["source"] == "catalog"]


def test_effective_companies_enabled_ids_includes_only_those_companies() -> None:
    career_pages = {"companies": [], "catalog": {"enabled_company_ids": ["sap", "siemens"]}}

    result = effective_companies(_DE_CONFIG, career_pages)

    ids = {c["id"] for c in result if c["source"] == "catalog"}
    assert ids == {"sap", "siemens"}


def test_effective_companies_matches_enabled_region() -> None:
    result = effective_companies(_DE_CONFIG, {"companies": [], **_SAP_SIEMENS_GOOGLE})

    ids = {c["id"] for c in result if c["source"] == "catalog"}
    assert "sap" in ids
    assert "siemens" in ids
    assert "google" not in ids  # US-only, DE region not matched even though allow-listed


def test_effective_companies_with_no_regions_and_full_allowlist_returns_all_catalog_companies() -> None:
    all_ids = [c.id for c in load_companies()]
    career_pages = {"companies": [], "catalog": {"enabled_company_ids": all_ids}}

    result = effective_companies(_NO_REGION_CONFIG, career_pages)

    assert len([c for c in result if c["source"] == "catalog"]) == len(load_companies())


def test_effective_companies_no_catalog_block_returns_only_custom() -> None:
    career_pages = {"companies": [{"name": "Custom Co", "career_url": "https://custom.example/careers"}]}

    result = effective_companies(_DE_CONFIG, career_pages)

    assert len(result) == 1
    assert result[0]["source"] == "custom"


def test_effective_companies_custom_entry_wins_on_duplicate_url() -> None:
    sap_url = next(c.career_url for c in load_companies() if c.id == "sap")
    career_pages = {
        "companies": [{"name": "SAP (custom override)", "career_url": sap_url}],
        "catalog": {"enabled_company_ids": ["sap"]},
    }

    result = effective_companies(_DE_CONFIG, career_pages)

    sap_entries = [c for c in result if c["career_url"].rstrip("/").lower() == sap_url.rstrip("/").lower()]
    assert len(sap_entries) == 1
    assert sap_entries[0]["source"] == "custom"


def test_effective_companies_excludes_by_industry_alias() -> None:
    career_pages = {"companies": [], **_SAP_SIEMENS_GOOGLE}
    config = {**_DE_CONFIG, "exclusions": {"industries": ["Software & IT"]}}

    result = effective_companies(config, career_pages)

    ids = {c["id"] for c in result if c["source"] == "catalog"}
    assert "sap" not in ids  # software_it
    assert "siemens" in ids  # manufacturing, unaffected


def test_effective_companies_unknown_industry_string_matches_nothing() -> None:
    career_pages = {"companies": [], **_SAP_SIEMENS_GOOGLE}
    config = {**_DE_CONFIG, "exclusions": {"industries": ["not-a-real-industry-name"]}}

    result = effective_companies(config, career_pages)

    assert len([c for c in result if c["source"] == "catalog"]) == len(effective_companies(_DE_CONFIG, career_pages))


def test_effective_companies_disabled_custom_entry_is_excluded() -> None:
    career_pages = {
        "companies": [{"name": "Custom Co", "career_url": "https://custom.example/careers", "enabled": False}]
    }

    result = effective_companies(_NO_REGION_CONFIG, career_pages)

    assert not any(c.get("name") == "Custom Co" for c in result)
