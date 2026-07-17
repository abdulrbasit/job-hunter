"""Offline statistical language detection for job postings.

Wraps lingua-py so the detection library is swappable without touching callers.
Restricted to job_hunter.core.builtin_filters.LANG_CODE_TO_NAME's language set
(the package's curated "relevant to job postings" universe) rather than lingua's
full catalog, to keep the detector small and fast.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from lingua import Language, LanguageDetectorBuilder

from job_hunter.core.builtin_filters import LANG_CODE_TO_NAME

_CONFIDENCE_THRESHOLD = 0.7

# lingua has no generic NORWEGIAN entry — it splits Norwegian into BOKMAL/NYNORSK.
# job_hunter's catalog uses the ISO 639-1 macro-code "no"; Bokmal is the common default.
_LINGUA_NAME_OVERRIDES: dict[str, str] = {"no": "BOKMAL"}


def _build_code_maps() -> tuple[dict[str, Language], dict[Language, str]]:
    code_to_language: dict[str, Language] = {}
    language_to_code: dict[Language, str] = {}
    for code, name in LANG_CODE_TO_NAME.items():
        attr = _LINGUA_NAME_OVERRIDES.get(code, name.upper())
        language = getattr(Language, attr, None)
        if language is None:
            continue
        code_to_language[code] = language
        language_to_code.setdefault(language, code)  # first code wins (pt over br, id over ms)
    return code_to_language, language_to_code


_CODE_TO_LANGUAGE, _LANGUAGE_TO_CODE = _build_code_maps()


@lru_cache(maxsize=1)
def _detector() -> object:
    return LanguageDetectorBuilder.from_languages(*_CODE_TO_LANGUAGE.values()).build()


@dataclass(frozen=True)
class LanguageDetection:
    code: str | None
    confidence: float


def _detect(text: str) -> LanguageDetection:
    values = _detector().compute_language_confidence_values(text)
    if not values:
        return LanguageDetection(None, 0.0)
    top = values[0]
    if top.value < _CONFIDENCE_THRESHOLD:
        return LanguageDetection(None, top.value)
    return LanguageDetection(_LANGUAGE_TO_CODE.get(top.language), top.value)


def detect_language(title: str, description: str = "") -> LanguageDetection:
    """Detect a posting's language: description first, title as fallback.

    Fails open (code=None) when text is empty or detection confidence is below
    threshold on both texts tried — callers must not exclude on an uncertain read.
    """
    description = description.strip()
    title = title.strip()
    primary = description or title
    if not primary:
        return LanguageDetection(None, 0.0)

    result = _detect(primary)
    if result.code is not None:
        return result
    if title and title != primary:
        title_result = _detect(title)
        if title_result.code is not None:
            return title_result
        return LanguageDetection(None, max(result.confidence, title_result.confidence))
    return result
