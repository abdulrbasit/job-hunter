"""Offline deterministic experience-level detection for job postings.

Bilingual (EN + DE) regex years-extraction plus title/level keyword matching,
backed by the package-owned taxonomy in job_hunter/catalog/experience_levels.json.
Extendable per language: add an entry to _YEARS_PATTERNS_BY_LANG and a
"keywords.<lang>" list per level in the catalog; an unlisted hunt language simply
falls back to the always-tried English patterns rather than erroring.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from job_hunter.models import ExperienceLevel, ExperienceLevelCatalog

_EN_WORD_NUM: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_DE_WORD_NUM: dict[str, int] = {
    "ein": 1,
    "eine": 1,
    "zwei": 2,
    "drei": 3,
    "vier": 4,
    "fünf": 5,
    "funf": 5,
    "sechs": 6,
    "sieben": 7,
    "acht": 8,
    "neun": 9,
    "zehn": 10,
}


def _num(token: str, word_map: dict[str, int]) -> int:
    return int(token) if token.isdigit() else word_map[token.lower()]


_YearsExtractor = Callable[[re.Match[str]], tuple[int, int | None]]
_YEARS_PATTERNS_BY_LANG: dict[str, list[tuple[re.Pattern[str], _YearsExtractor]]] = {
    "en": [
        (re.compile(r"(\d+)\s*-\s*(\d+)\+?\s*years?\b", re.I), lambda m: (int(m.group(1)), int(m.group(2)))),
        (re.compile(r"(\d+)\s*\+\s*years?\b", re.I), lambda m: (int(m.group(1)), None)),
        (
            re.compile(
                r"(?:at least|minimum of|min\.?)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+years?\b",
                re.I,
            ),
            lambda m: (_num(m.group(1), _EN_WORD_NUM), None),
        ),
        (re.compile(r"(\d+)\s+years?\s*(?:of\s+)?experience\b", re.I), lambda m: (int(m.group(1)), None)),
    ],
    "de": [
        (re.compile(r"(\d+)\s*-\s*(\d+)\+?\s*jahre?n?\b", re.I), lambda m: (int(m.group(1)), int(m.group(2)))),
        (re.compile(r"mind(?:estens)?\.?\s*(\d+)\s*jahre?n?\b", re.I), lambda m: (int(m.group(1)), None)),
        (
            re.compile(
                r"(ein|eine|zwei|drei|vier|f[uü]nf|sechs|sieben|acht|neun|zehn)j[aä]hrige[rn]?\s*berufserfahrung", re.I
            ),
            lambda m: (_num(m.group(1), _DE_WORD_NUM), None),
        ),
        (re.compile(r"(\d+)\s*jahre?n?\s*(?:berufserfahrung|erfahrung)\b", re.I), lambda m: (int(m.group(1)), None)),
    ],
}


@lru_cache(maxsize=1)
def load_experience_levels() -> list[ExperienceLevel]:
    raw = resources.files("job_hunter").joinpath("catalog", "experience_levels.json").read_text(encoding="utf-8")
    return ExperienceLevelCatalog.model_validate_json(raw).levels


def experience_level_by_id(level_id: str) -> ExperienceLevel | None:
    return next((level for level in load_experience_levels() if level.id == level_id), None)


_BASE_LANGS = ("en", "de")


def _langs_to_try(hunt_language: str) -> list[str]:
    """Both bundled languages are always tried (bilingual postings are common,
    e.g. a German JD with an English title) — hunt_language only adds a language
    beyond the bundled EN+DE set, for future extensibility."""
    langs = list(_BASE_LANGS)
    if hunt_language and hunt_language not in langs:
        langs.append(hunt_language)
    return langs


def _extract_years(text: str, hunt_language: str) -> tuple[int, int | None] | None:
    for lang in _langs_to_try(hunt_language):
        for pattern, extract in _YEARS_PATTERNS_BY_LANG.get(lang, []):
            match = pattern.search(text)
            if match:
                return extract(match)
    return None


def _match_keyword(text: str, hunt_language: str) -> ExperienceLevel | None:
    for level in load_experience_levels():
        for lang in _langs_to_try(hunt_language):
            for term in level.keywords.get(lang, []):
                if re.search(rf"\b{re.escape(term)}\b", text, re.I):
                    return level
    return None


@dataclass(frozen=True)
class ExperienceDetection:
    level_id: str | None
    min_years: int | None
    max_years: int | None
    confident: bool


def detect_experience(title: str, description: str, hunt_language: str = "en") -> ExperienceDetection:
    """Detect a posting's required experience: years-regex first, title/level keywords second.

    Years-regex is the precise signal and its pattern set is small (a handful per
    language), so it's cheap to run once over the full text regardless of length —
    checked first so an explicit "5+ years" always wins over a coarser level bucket.
    Keyword matching is the expensive part (every level's keywords, per language),
    so once years-regex comes up empty, the short title is tried before the much
    longer description — most keyword-resolvable postings ("Senior Engineer",
    "Werkstudent Marketing") never need the full-description scan at all.

    Fails open (confident=False) when nothing matches — callers must not exclude
    on an unconfident read.
    """
    title = title.strip()
    description = description.strip()
    if not title and not description:
        return ExperienceDetection(None, None, None, False)

    years = _extract_years(f"{description}\n{title}".strip(), hunt_language)
    if years is not None:
        return ExperienceDetection(None, years[0], years[1], True)

    if title:
        level = _match_keyword(title, hunt_language)
        if level is not None:
            return ExperienceDetection(level.id, level.min_years, level.max_years, True)
    if description:
        level = _match_keyword(description, hunt_language)
        if level is not None:
            return ExperienceDetection(level.id, level.min_years, level.max_years, True)

    return ExperienceDetection(None, None, None, False)
