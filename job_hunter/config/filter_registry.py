"""Typed registry for standardized filter groups in job_hunter.yml."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from job_hunter.core.builtin_filters import LANG_CODE_TO_NAME
from job_hunter.core.utils import normalize_company_name
from job_hunter.models import FilterConfig, FilterEntryConfig


@dataclass(frozen=True)
class FilterFile:
    name: str
    description: str
    entries: tuple[FilterEntryConfig, ...]
    _exact_values: frozenset[str] = field(init=False, repr=False)
    _company_exact_values: frozenset[str] = field(init=False, repr=False)
    _contains_pattern: re.Pattern[str] | None = field(init=False, repr=False)
    _regex_pattern: re.Pattern[str] | None = field(init=False, repr=False)
    _fallback_regex_patterns: tuple[re.Pattern[str], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        values = tuple(entry.value for entry in self.entries)

        object.__setattr__(self, "_exact_values", frozenset(value.casefold() for value in values))
        object.__setattr__(
            self,
            "_company_exact_values",
            frozenset(filter(None, (normalize_company_name(value) for value in values))),
        )
        object.__setattr__(self, "_contains_pattern", _compile_contains(values))
        regex_pattern, fallback_patterns = _compile_regexes(values)
        object.__setattr__(self, "_regex_pattern", regex_pattern)
        object.__setattr__(self, "_fallback_regex_patterns", fallback_patterns)

    @property
    def values(self) -> list[str]:
        return [entry.value for entry in self.entries]

    def matches(self, text: str, *, normalize_company: bool = False) -> bool:
        exact_value = normalize_company_name(text) if normalize_company else text.casefold()
        exact_values = self._company_exact_values if normalize_company else self._exact_values
        return bool(
            (exact_value and exact_value in exact_values)
            or (self._contains_pattern and self._contains_pattern.search(text))
            or (self._regex_pattern and self._regex_pattern.search(text))
            or any(pattern.search(text) for pattern in self._fallback_regex_patterns)
        )


def _compile_contains(values: tuple[str, ...]) -> re.Pattern[str] | None:
    if not values:
        return None
    alternatives = (rf"\b{re.escape(value)}\b" for value in values)
    return re.compile("|".join(f"(?:{pattern})" for pattern in alternatives), re.IGNORECASE)


def _compile_regexes(
    values: tuple[str, ...],
) -> tuple[re.Pattern[str] | None, tuple[re.Pattern[str], ...]]:
    combinable: list[str] = []
    fallback: list[re.Pattern[str]] = []
    for value in values:
        try:
            compiled = re.compile(value, re.IGNORECASE)
        except re.error:
            continue
        if compiled.groups:
            fallback.append(compiled)
        else:
            combinable.append(value)
    if not combinable:
        return None, tuple(fallback)
    try:
        combined = re.compile("|".join(f"(?:{value})" for value in combinable), re.IGNORECASE)
    except re.error:
        fallback.extend(re.compile(value, re.IGNORECASE) for value in combinable)
        return None, tuple(fallback)
    return combined, tuple(fallback)


@dataclass(frozen=True)
class FilterRegistry:
    files: dict[str, FilterFile]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> FilterRegistry:
        files: dict[str, FilterFile] = {}
        raw_filters = config.get("filters") or {}
        if not raw_filters and config.get("exclusions"):
            exclusions = config["exclusions"]
            raw_filters = {
                "excluded_companies": {
                    "description": "Legacy companies",
                    "entries": [{"value": str(value)} for value in exclusions.get("companies", []) or []],
                },
                "excluded_titles": {
                    "description": "Legacy titles",
                    "entries": [{"value": str(value)} for value in exclusions.get("title_terms", []) or []],
                },
                "excluded_industries": {
                    "description": "Legacy industries",
                    "entries": [{"value": str(value)} for value in exclusions.get("industries", []) or []],
                },
            }
        for name, raw in raw_filters.items():
            parsed = FilterConfig.model_validate(raw)
            files[str(name)] = FilterFile(
                name=str(name),
                description=parsed.description,
                entries=tuple(parsed.entries),
            )
        return cls(files)

    def file(self, name: str) -> FilterFile | None:
        return self.files.get(name)

    def names(self) -> list[str]:
        return sorted(self.files)

    @property
    def allowed_languages(self) -> frozenset[str]:
        file = self.file("languages")
        if not file:
            return frozenset()
        return frozenset(LANG_CODE_TO_NAME.get(value.casefold(), value.casefold()) for value in file.values)
