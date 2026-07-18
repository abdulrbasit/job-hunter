"""Package-owned filter definitions and matching bound to user scalar choices."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from job_hunter.core.builtin_filters import LANG_CODE_TO_NAME
from job_hunter.core.experience import load_experience_levels
from job_hunter.core.utils import normalize_company_name
from job_hunter.filters.catalog import load_filter_catalog
from job_hunter.models import FilterMatchMode, FilterType

FILTER_TYPES: dict[str, FilterType] = {
    "excluded_companies": FilterType(
        name="excluded_companies",
        description="Companies excluded from results",
        mode=FilterMatchMode.CONTAINS,
        normalize_company=True,
    ),
    "excluded_titles": FilterType(
        name="excluded_titles",
        description="Title terms excluded from results",
        mode=FilterMatchMode.CONTAINS,
    ),
    "excluded_industries": FilterType(
        name="excluded_industries",
        description="Industries excluded from results",
        mode=FilterMatchMode.CONTAINS,
        taxonomy="industries",
    ),
    "hunt_languages": FilterType(
        name="hunt_languages",
        description="ISO language codes allowed during hunts",
        mode=FilterMatchMode.EXACT,
        taxonomy="languages",
    ),
    "experience_levels": FilterType(
        name="experience_levels",
        description="Experience levels you're targeting — postings whose required-experience "
        "range doesn't overlap any selected level are excluded",
        mode=FilterMatchMode.EXACT,
        taxonomy="experience_levels",
    ),
    "posting_types": FilterType(
        name="posting_types",
        description="Student posting types to include; empty includes every type",
        mode=FilterMatchMode.EXACT,
        taxonomy="posting_types",
    ),
}

_LANG_NAME_TO_CODE: dict[str, str] = {}
for _code, _name in LANG_CODE_TO_NAME.items():
    _LANG_NAME_TO_CODE.setdefault(_name, _code)


def _scalar_values(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(value).strip() for value in raw if str(value).strip()]
    if not isinstance(raw, dict):
        return []
    return [
        str(entry.get("value") if isinstance(entry, dict) else entry).strip()
        for entry in raw.get("entries", []) or []
        if str(entry.get("value") if isinstance(entry, dict) else entry).strip()
    ]


def canonicalize_filter_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a runtime copy with only known filter types and scalar lists."""
    result = deepcopy(config)
    raw_filters = result.get("filters") or {}
    if not raw_filters and isinstance(result.get("exclusions"), dict):
        exclusions = result["exclusions"]
        raw_filters = {
            "excluded_companies": exclusions.get("companies", []) or [],
            "excluded_titles": exclusions.get("title_terms", []) or [],
            "excluded_industries": exclusions.get("industries", []) or [],
        }
    if not isinstance(raw_filters, dict):
        result["filters"] = {}
        return result
    canonical: dict[str, list[str]] = {}
    for name in FILTER_TYPES:
        source_name = "languages" if name == "hunt_languages" and "hunt_languages" not in raw_filters else name
        if source_name not in raw_filters:
            continue
        values = _scalar_values(raw_filters[source_name])
        if name == "hunt_languages":
            values = [_LANG_NAME_TO_CODE.get(value.casefold(), value.casefold()) for value in values]
        canonical[name] = list(dict.fromkeys(values))
    result["filters"] = canonical
    return result


def filter_values(config: dict[str, Any], name: str) -> list[str]:
    return list((canonicalize_filter_config(config).get("filters") or {}).get(name, []))


def validate_filter_choices(config: dict[str, Any]) -> list[str]:
    filters = canonicalize_filter_config(config).get("filters") or {}
    valid_industries = {industry.id for industry in load_filter_catalog().industries}
    invalid_industries = sorted(set(filters.get("excluded_industries", [])) - valid_industries)
    invalid_languages = sorted(set(filters.get("hunt_languages", [])) - set(LANG_CODE_TO_NAME))
    from job_hunter.core.posting_types import STUDENT_POSTING_TYPES

    valid_levels = {level.id for level in load_experience_levels()} | {
        "student",
        "entry",
        "mid",
        "senior",
        "expert",
        "management",
        "executive",
    }
    invalid_levels = sorted(set(filters.get("experience_levels", [])) - valid_levels)
    invalid_posting_types = sorted(set(filters.get("posting_types", [])) - set(STUDENT_POSTING_TYPES))
    errors: list[str] = []
    if invalid_industries:
        errors.append(f"filters.excluded_industries contains unknown package IDs: {', '.join(invalid_industries)}")
    if invalid_languages:
        errors.append(f"filters.hunt_languages contains unknown ISO codes: {', '.join(invalid_languages)}")
    if invalid_levels:
        errors.append(f"filters.experience_levels contains unknown package IDs: {', '.join(invalid_levels)}")
    if invalid_posting_types:
        errors.append(f"filters.posting_types contains unknown package IDs: {', '.join(invalid_posting_types)}")
    return errors


def filter_options() -> dict[str, Any]:
    languages: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for code, name in LANG_CODE_TO_NAME.items():
        if name not in seen_names:
            languages.append({"code": code, "name": name.title()})
            seen_names.add(name)
    return {
        "types": [definition.model_dump(mode="json") for definition in FILTER_TYPES.values()],
        "industries": [{"id": industry.id, "label": industry.label} for industry in load_filter_catalog().industries],
        "languages": languages,
        "experience_levels": [
            {
                "id": group,
                "label": group.replace("_", " ").title(),
            }
            for group in ("student", "entry", "mid", "senior", "expert", "management", "executive")
        ],
        "posting_types": [
            {"id": value, "label": value.replace("_", " ").title()}
            for value in __import__(
                "job_hunter.core.posting_types", fromlist=["STUDENT_POSTING_TYPES"]
            ).STUDENT_POSTING_TYPES
        ],
    }


def _expanded_values(definition: FilterType, values: list[str]) -> tuple[str, ...]:
    if definition.taxonomy != "industries":
        return tuple(values)
    selected = {value.casefold() for value in values}
    expanded: list[str] = []
    for industry in load_filter_catalog().industries:
        if industry.id.casefold() in selected:
            expanded.extend((industry.id, industry.label, *industry.aliases))
    return tuple(dict.fromkeys([*values, *expanded]))


@dataclass(frozen=True)
class BoundFilter:
    definition: FilterType
    values: tuple[str, ...]
    _exact: frozenset[str] = field(init=False, repr=False)
    _contains: re.Pattern[str] | None = field(init=False, repr=False)

    def __post_init__(self) -> None:
        expanded = _expanded_values(self.definition, list(self.values))
        normalized = tuple(self._normalize(value) for value in expanded)
        object.__setattr__(self, "_exact", frozenset(filter(None, normalized)))
        pattern = (
            "|".join(rf"\b{re.escape(value)}\b" for value in normalized if value)
            if self.definition.mode != FilterMatchMode.EXACT
            else ""
        )
        object.__setattr__(self, "_contains", re.compile(pattern, re.IGNORECASE) if pattern else None)

    def _normalize(self, value: str) -> str:
        return normalize_company_name(value) if self.definition.normalize_company else value.casefold()

    def matches(self, text: str) -> bool:
        normalized = self._normalize(text)
        if self.definition.mode == FilterMatchMode.EXACT:
            return normalized in self._exact
        return bool(normalized in self._exact or (self._contains and self._contains.search(normalized)))


@lru_cache(maxsize=256)
def _bind_filter(name: str, values: tuple[str, ...]) -> BoundFilter:
    """Compile one immutable matcher per package type and user choice tuple."""
    return BoundFilter(FILTER_TYPES[name], values)


@dataclass(frozen=True)
class FilterSet:
    bound: dict[str, BoundFilter]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> FilterSet:
        canonical = canonicalize_filter_config(config).get("filters") or {}
        return cls({name: _bind_filter(name, tuple(canonical[name])) for name in FILTER_TYPES if canonical.get(name)})

    def names(self) -> list[str]:
        return sorted(self.bound)

    def values(self, name: str) -> list[str]:
        match = self.bound.get(name)
        return list(match.values) if match else []

    def matches(self, name: str, text: str) -> bool:
        match = self.bound.get(name)
        return bool(match and match.matches(text))
