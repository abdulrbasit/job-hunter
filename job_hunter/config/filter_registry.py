"""Typed registry for standardized filter groups in job_hunter.yml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from job_hunter.models import FilterConfig, FilterEntryConfig

_LANG_CODE_TO_NAME = {
    "en": "english",
    "de": "german",
    "fr": "french",
    "it": "italian",
    "es": "spanish",
    "pt": "portuguese",
    "br": "portuguese",
    "nl": "dutch",
    "pl": "polish",
    "ru": "russian",
    "cs": "czech",
    "sk": "slovak",
    "hu": "hungarian",
    "ro": "romanian",
    "sv": "swedish",
    "da": "danish",
    "no": "norwegian",
    "fi": "finnish",
    "el": "greek",
    "tr": "turkish",
    "ar": "arabic",
    "he": "hebrew",
    "zh": "chinese",
    "ja": "japanese",
    "ko": "korean",
    "hi": "hindi",
    "id": "indonesian",
    "ms": "indonesian",
    "th": "thai",
    "vi": "vietnamese",
    "uk": "ukrainian",
    "ca": "catalan",
}

_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(gmbh|ag|inc|inc\.|ltd|ltd\.|llc|plc|se|sa|s\.a\.|corp|corp\.|corporation|group)\b",
    re.IGNORECASE,
)


def _normalize_company(value: str) -> str:
    normalized = _CORPORATE_SUFFIX_RE.sub("", value)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower())
    return " ".join(normalized.split())


@dataclass(frozen=True)
class FilterFile:
    name: str
    description: str
    entries: tuple[FilterEntryConfig, ...]

    @property
    def values(self) -> list[str]:
        return [entry.value for entry in self.entries]

    def matches(self, text: str, *, normalize_company: bool = False) -> bool:
        for entry in self.entries:
            if entry.match in (None, "exact"):
                left = _normalize_company(text) if normalize_company else text.casefold()
                right = _normalize_company(entry.value) if normalize_company else entry.value.casefold()
                if left and left == right:
                    return True
            if entry.match in (None, "contains") and re.search(
                r"\b" + re.escape(entry.value) + r"\b", text, re.IGNORECASE
            ):
                return True
            if entry.match in (None, "regex"):
                try:
                    if re.search(entry.value, text, re.IGNORECASE):
                        return True
                except re.error:
                    continue
        return False


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
        return frozenset(_LANG_CODE_TO_NAME.get(value.casefold(), value.casefold()) for value in file.values)
