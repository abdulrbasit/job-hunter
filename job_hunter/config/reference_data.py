"""Loaders for package-owned reference catalogs: countries.json and filters.json.

Read-only, versioned JSON shipped with the package (not user-editable, unlike
config/job_hunter.yml). All bundled reference databases live in
job_hunter/catalog/ (companies.json, countries.json, filters.json — future
databases go there too). Validated through the existing Pydantic dependency
(see job_hunter/models.py for the same pattern) rather than a new schema tool.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from pydantic import BaseModel, ConfigDict

from job_hunter.filters.catalog import load_filter_catalog
from job_hunter.models import CareerStage, FilterCatalog


class CountryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    aliases: list[str] = []
    languages: list[str] = []
    reviewed_languages: list[str] = []
    city_aliases: list[str] = []


class _CountriesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    count: int
    countries: list[CountryEntry]


@lru_cache(maxsize=1)
def load_countries() -> list[CountryEntry]:
    raw = resources.files("job_hunter").joinpath("catalog", "countries.json").read_text(encoding="utf-8")
    return _CountriesFile.model_validate_json(raw).countries


def load_filters() -> FilterCatalog:
    """Compatibility name for the package-owned filter catalog loader."""
    return load_filter_catalog()


def country_codes() -> set[str]:
    return {c.code for c in load_countries()}


def career_stage_names() -> list[str]:
    return list(load_filters().career_stages.keys())


def career_stage(name: str) -> CareerStage:
    stages = load_filters().career_stages
    return stages.get(name, stages["custom"])


# Legacy default used before career_stage existed; "custom" preserves it exactly.
_LEGACY_MAX_YEARS_FALLBACK = 4

# "leadership" has no cap; validation/scoring compare `years > max_years` with a
# plain int, so "no cap" is a sentinel rather than None (avoids an Optional
# refactor across job_hunter/pipeline/stages/validation.py and scoring.py).
_NO_CAP_SENTINEL = 999


def resolve_title_exclusions(config: dict) -> list[str]:
    """User filter terms unioned with active career_stage's reviewed hard excludes."""
    from job_hunter.filters import filter_values

    user_terms = filter_values(config, "excluded_titles")
    stage_terms = career_stage(str(config.get("career_stage") or "custom")).exclude
    return list(dict.fromkeys([*user_terms, *stage_terms]))


def resolve_max_years_experience(config: dict) -> int:
    """Explicit scoring.max_years_experience_required wins; else the career_stage default; else the legacy fallback."""
    scoring = config.get("scoring", {}) or {}
    explicit = scoring.get("max_years_experience_required")
    if explicit is not None:
        return int(explicit)
    stage_name = str(config.get("career_stage") or "custom")
    if stage_name == "custom":
        return _LEGACY_MAX_YEARS_FALLBACK
    stage_default = career_stage(stage_name).max_years_experience
    return int(stage_default) if stage_default is not None else _NO_CAP_SENTINEL


def preferred_title_terms(config: dict) -> list[str]:
    """Career-stage terms that should rank a job higher — soft signal, never mandatory.

    ponytail: not yet wired into a ranking/sort call site — there's no results list
    to rank against until the Phase 4 Candidates UI exists. Upgrade trigger: Phase 4.
    """
    return list(career_stage(str(config.get("career_stage") or "custom")).prefer)
