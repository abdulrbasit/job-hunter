"""Loads and validates job_hunter/catalog/companies.json (package resource, not user-editable)."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from job_hunter.config.reference_data import country_codes as _valid_country_codes
from job_hunter.filters.catalog import load_filter_catalog
from job_hunter.models import Location, LocationScope


class CompanyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    career_url: str
    country_codes: list[str]
    city_tags: list[str] = []
    industry_ids: list[str]
    remote_country_codes: list[str] = []
    ats_platform: str | None = None
    verified_at: str

    @field_validator("career_url")
    @classmethod
    def _career_url_is_https(cls, value: str) -> str:
        if urlsplit(value).scheme != "https":
            raise ValueError(f"career_url must be https ({value!r})")
        return value

    @field_validator("country_codes")
    @classmethod
    def _country_codes_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("country_codes must not be empty")
        return value

    def location_evidence(self) -> list[Location]:
        """Return exact canonical evidence used by the company location gate."""
        from job_hunter.locations import canonicalize_runtime_location

        evidence = [
            location
            for city_name in self.city_tags
            for country in self.country_codes
            for location in canonicalize_runtime_location(city_name, country)
        ]
        evidence.extend(Location(country=code, scope=LocationScope.COUNTRY) for code in self.country_codes)
        evidence.extend(
            Location(country=code, scope=LocationScope.REMOTE_COUNTRY) for code in self.remote_country_codes
        )
        return evidence


class _CompaniesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    count: int
    companies: list[CompanyEntry]

    @model_validator(mode="after")
    def _cross_reference_and_uniqueness(self) -> _CompaniesFile:
        errors: list[str] = []
        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        valid_countries = _valid_country_codes()
        valid_industries = {industry.id for industry in load_filter_catalog().industries}

        for company in self.companies:
            if company.id in seen_ids:
                errors.append(f"duplicate company id {company.id!r}")
            seen_ids.add(company.id)

            normalized_url = company.career_url.rstrip("/").lower()
            if normalized_url in seen_urls:
                errors.append(f"duplicate career_url {company.career_url!r}")
            seen_urls.add(normalized_url)

            unknown_countries = set(company.country_codes) - valid_countries
            if unknown_countries:
                errors.append(f"{company.id}: unknown country_codes {sorted(unknown_countries)}")

            unknown_industries = set(company.industry_ids) - valid_industries
            if unknown_industries:
                errors.append(f"{company.id}: unknown industry_ids {sorted(unknown_industries)}")

        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache(maxsize=1)
def load_companies() -> list[CompanyEntry]:
    raw = resources.files("job_hunter.catalog").joinpath("companies.json").read_text(encoding="utf-8")
    return _CompaniesFile.model_validate_json(raw).companies
