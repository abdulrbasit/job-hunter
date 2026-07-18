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

from job_hunter.core.experience import ExperienceLevel, load_experience_levels
from job_hunter.filters.catalog import load_filter_catalog
from job_hunter.models import FilterCatalog


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


def experience_level_names() -> list[str]:
    return [level.id for level in load_experience_levels()]


EXPERIENCE_GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "student": ("student_intern", "student_working_student", "student_thesis"),
    "entry": ("entry", "junior", "associate"),
    "mid": ("mid",),
    "senior": ("senior",),
    "expert": ("lead", "staff", "principal", "expert"),
    "management": ("manager", "director"),
    "executive": ("vp", "c_level"),
}


def experience_group_names() -> list[str]:
    return list(EXPERIENCE_GROUP_MEMBERS)


def resolve_experience_group_ids(values: list[str]) -> set[str]:
    """Resolve public group IDs and legacy detailed IDs without rewriting config."""
    resolved: set[str] = set()
    for value in values:
        if value in EXPERIENCE_GROUP_MEMBERS:
            resolved.add(value)
            continue
        resolved.update(group for group, members in EXPERIENCE_GROUP_MEMBERS.items() if value in members)
    return resolved


def expanded_experience_level_ids(values: list[str]) -> list[str]:
    expand_groups = all(value in EXPERIENCE_GROUP_MEMBERS for value in values)
    expanded: list[str] = []
    for value in values:
        members = EXPERIENCE_GROUP_MEMBERS.get(value, (value,)) if expand_groups else (value,)
        expanded.extend(members)
    return list(dict.fromkeys(expanded))


def student_mode(config: dict) -> bool:
    from job_hunter.filters import filter_values

    return "student" in resolve_experience_group_ids(filter_values(config, "experience_levels"))


def experience_level(level_id: str) -> ExperienceLevel | None:
    return next((level for level in load_experience_levels() if level.id == level_id), None)


# Screening/scoring compare `years > max_years` with a plain int, so "no cap" is a
# sentinel rather than None (avoids an Optional refactor across scoring.py).
_NO_CAP_SENTINEL = 999


def resolve_experience_range(config: dict) -> tuple[int, int | None]:
    """Union of the user's selected experience_levels' [min_years, max_years].

    An empty/unset selection is a defensive no-op fallback (real saved configs always
    have at least one level per the schema) rather than a second competing default.
    """
    from job_hunter.filters import filter_values

    selected = expanded_experience_level_ids(filter_values(config, "experience_levels")) or experience_level_names()
    levels = [level for level in (experience_level(level_id) for level_id in selected) if level is not None]
    if not levels:
        return 0, None
    min_years = min(level.min_years for level in levels)
    if any(level.max_years is None for level in levels):
        return min_years, None
    return min_years, max(level.max_years for level in levels)  # type: ignore[type-var]


def resolve_max_years_experience(config: dict) -> int:
    """Explicit scoring.max_years_experience_required wins; else the experience_levels-derived max."""
    scoring = config.get("scoring", {}) or {}
    explicit = scoring.get("max_years_experience_required")
    if explicit is not None:
        return int(explicit)
    _, max_years = resolve_experience_range(config)
    return int(max_years) if max_years is not None else _NO_CAP_SENTINEL


def resolve_title_exclusions(config: dict) -> list[str]:
    """User's own excluded_titles filter."""
    from job_hunter.filters import filter_values

    return list(filter_values(config, "excluded_titles"))
