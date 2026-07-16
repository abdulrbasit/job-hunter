"""Package-owned quality filters shared across discovery and screening."""

from __future__ import annotations

import json
from importlib import resources

STALE_INDICATORS: tuple[str, ...] = (
    "no longer available",
    "this job has expired",
    "position has been filled",
    "not accepting applications",
    "applications are closed",
    "job is closed",
    "posting has closed",
)

EXCLUDED_LISTING_URL_PATTERNS: tuple[str, ...] = (
    r"linkedin\.com/jobs/search",
    r"linkedin\.com/jobs/[^/?#]+-jobs",
    r"linkedin\.com/jobs/collections",
    r"linkedin\.com/jobs/remote-",
    r"linkedin\.com/jobs/[a-z]+-stellen",
    r"linkedin\.com/jobs/[a-z]+-stellenangebote",
)

LISTING_ONLY_PATHS: frozenset[str] = frozenset(
    {"/jobs", "/careers", "/positions", "/openings", "/vacancies", "/work-with-us", "/join-us"}
)

CONTRACT_PHRASES: frozenset[str] = frozenset(
    {
        "employment type: contract",
        "employment type : contract",
        "this is a contract role",
        "this is a contract position",
        "contract-only",
        "contractors only",
        "fixed-term contract",
    }
)

MAX_POSTING_AGE_DAYS = 45

RESTRICTION_PHRASES: tuple[str, ...] = (
    "{} only",
    "{}-only",
    "only {}",
    "{}-based candidates only",
    "must be based in {}",
    "must be located in {}",
    "must reside in {}",
    "must live in {}",
    "authorized to work in {}",
    "authorized to work in the {}",
    "work authorization in {}",
    "work authorization required in {}",
    "candidates in {} only",
    "candidates from {} only",
    "applicants from {} only",
    "open to {} candidates only",
    "open to candidates in {}",
    "based in {} required",
    "relocation to {} required",
    "remote/{}",
    "remote - {}",
    "remote – {}",
    "remote in {}",
    "{} remote",
    "({}) remote",
    "(remote/{}) ",
)

US_ONLY_PHRASES: frozenset[str] = frozenset(
    {
        "us remote",
        "us-remote",
        "remote - united states",
        "remote – united states",
        "(us remote)",
        "us/can remote",
        "us/ca remote",
        "remote within the us",
        "within the united states",
        "canada or mexico",
        "mexico or canada",
        "remote (us only)",
    }
)

LANG_CODE_TO_NAME: dict[str, str] = {
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


def _load_language_indicators() -> dict[str, tuple[str, ...]]:
    raw = resources.files("job_hunter.catalog").joinpath("filters.json").read_text(encoding="utf-8")
    languages = json.loads(raw)["languages"]
    return {name: tuple(data["indicators"]) for name, data in languages.items()}


LANGUAGE_INDICATORS = _load_language_indicators()
