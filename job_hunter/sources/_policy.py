"""Filtering and dedupe policy for discovered job postings."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from job_hunter.config.defaults import EXCLUDED_LISTING_URL_PATTERNS, LANGUAGE_INDICATORS, STALE_INDICATORS
from job_hunter.core.utils import title_matches
from job_hunter.models import JobPosting
from job_hunter.sources.search_providers import canonicalize_url

logger = logging.getLogger(__name__)
MAX_POSTING_AGE_DAYS = 45

_LISTING_ONLY_PATHS = {
    "/jobs",
    "/careers",
    "/positions",
    "/openings",
    "/vacancies",
    "/work-with-us",
    "/join-us",
}

_GERMAN_WORD_RE = re.compile(r"[a-z\u00e4\u00f6\u00fc\u00df]+", re.IGNORECASE)
_GERMAN_MIN_WORDS = 18
_GERMAN_MIN_HITS = 6
_GERMAN_MIN_UNIQUE_HITS = 4
_GERMAN_LANGUAGE_MARKERS = {
    "als",
    "auf",
    "aus",
    "bei",
    "das",
    "dein",
    "deine",
    "deinem",
    "deinen",
    "deiner",
    "dem",
    "den",
    "der",
    "des",
    "dich",
    "die",
    "du",
    "ein",
    "eine",
    "einem",
    "einen",
    "einer",
    "f\u00fcr",
    "fuer",
    "ihre",
    "ihren",
    "ihr",
    "im",
    "ist",
    "mit",
    "nicht",
    "oder",
    "sich",
    "sind",
    "sowie",
    "und",
    "uns",
    "unser",
    "unsere",
    "von",
    "wir",
    "zu",
    "zum",
    "zur",
}


def _looks_like_german_text(text: str) -> bool:
    words = _GERMAN_WORD_RE.findall(text.lower())
    if len(words) < _GERMAN_MIN_WORDS:
        return False

    hits = [word for word in words if word in _GERMAN_LANGUAGE_MARKERS]
    return len(hits) >= _GERMAN_MIN_HITS and len(set(hits)) >= _GERMAN_MIN_UNIQUE_HITS


_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(gmbh|ag|inc|inc\.|ltd|ltd\.|llc|plc|se|sa|s\.a\.|corp|corp\.|corporation|group)\b",
    re.IGNORECASE,
)


def normalize_company_name(company: str) -> str:
    normalized = _CORPORATE_SUFFIX_RE.sub("", company or "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower())
    return " ".join(normalized.split())


@dataclass(frozen=True)
class JobPolicy:
    config: dict

    @property
    def exclusions(self) -> dict:
        return self.config.get("exclusions", {}) or {}

    @property
    def excluded_title_terms(self) -> list[str]:
        return [str(term) for term in self.exclusions.get("title_terms", []) or []]

    @property
    def excluded_companies(self) -> list[str]:
        return [str(company) for company in self.exclusions.get("companies", []) or []]

    @property
    def excluded_industries(self) -> list[str]:
        return [str(industry) for industry in self.exclusions.get("industries", []) or []]

    @property
    def excluded_languages(self) -> list[str]:
        return [str(language).strip().lower() for language in self.exclusions.get("languages", []) or []]

    def is_valid_job_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")

        if not path:
            return False
        if path in _LISTING_ONLY_PATHS:
            return False

        segments = [s for s in path.split("/") if s]
        return len(segments) >= 2

    def is_excluded_url(self, url: str) -> bool:
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in EXCLUDED_LISTING_URL_PATTERNS)

    def is_stale_posting(self, title: str, snippet: str) -> bool:
        combined = (title + " " + snippet).lower()
        return any(indicator in combined for indicator in STALE_INDICATORS)

    def is_excluded_company(self, company: str) -> bool:
        company_norm = normalize_company_name(company)
        return bool(company_norm) and any(normalize_company_name(e) == company_norm for e in self.excluded_companies)

    def is_excluded_industry(self, snippet: str) -> bool:
        return any(kw in snippet.lower() for kw in self.excluded_industries)

    def posting_date_status(self, posted: str) -> str:
        if not posted:
            return "missing"
        try:
            value = datetime.fromisoformat(str(posted)[:10]).replace(tzinfo=UTC)
        except ValueError:
            return "invalid_date"
        today = datetime.now(UTC)
        if value > today + timedelta(days=1):
            return "future_date"
        if value < today - timedelta(days=MAX_POSTING_AGE_DAYS):
            return "stale_date"
        return "current"

    def is_german(self, title: str, snippet: str) -> bool:
        return self.is_excluded_language(title, snippet, language="german")

    def is_excluded_language(self, title: str, snippet: str, *, language: str | None = None) -> bool:
        excluded_languages = [language for language in self.excluded_languages if language]
        if language:
            if language.lower() not in excluded_languages:
                return False
            languages = [language.lower()]
        else:
            languages = excluded_languages
        if not languages:
            return False

        combined = (title + " " + snippet).lower()
        for lang in languages:
            indicators = [
                str(value).strip().lower() for value in LANGUAGE_INDICATORS.get(lang, ()) if str(value).strip()
            ]
            if indicators and any(indicator in combined for indicator in indicators):
                return True
            if lang == "german" and _looks_like_german_text(combined):
                return True
        return False

    def accepts_job_content(self, job: dict, title_filters: list[str]) -> bool:
        return self.rejection_reason(job, title_filters) == ""

    def rejection_reason(self, job: dict, title_filters: list[str]) -> str:
        title = job.get("title", "")
        company = job.get("company", "")
        snippet = job.get("snippet", "")

        if not str(title).strip() or not str(company).strip():
            return "missing_identity"
        if str(title).strip().lower() == "unknown role" or str(company).strip().lower() == "unknown company":
            return "missing_identity"
        if title_filters and not title_matches(title, title_filters, self.excluded_title_terms):
            logger.info("[skip] Title not in filters: %s", title[:60])
            return "excluded_title"
        if self.is_excluded_company(company):
            logger.info("[skip] Excluded company: %s", company[:60])
            return "excluded_company"
        if self.is_stale_posting(title, snippet):
            logger.info("[skip] Stale/closed posting: %s", title[:60])
            return "stale_content"
        if self.is_excluded_language(title, snippet):
            logger.info("[skip] Excluded-language posting: %s", title[:60])
            return "excluded_language"
        if self.is_excluded_industry(snippet):
            logger.info("[skip] Excluded industry: %s", title[:60])
            return "excluded_industry"
        date_status = self.posting_date_status(str(job.get("posted") or ""))
        if date_status not in {"current", "missing"}:
            logger.info("[skip] %s: %s", date_status, title[:60])
            return date_status
        return ""

    def has_wrong_location(self, job: dict, region_cfg: dict) -> bool:
        """Return True if job location doesn't match any allowed location in region_cfg."""
        allowed = region_cfg.get("locations") or []
        if not allowed:
            return False
        job_location = str(job.get("location") or "")
        if not job_location:
            return False
        from job_hunter.core.utils import location_matches

        return not any(location_matches(job_location, loc) for loc in allowed)

    def accepts_search_result_url(self, url: str, title: str, snippet: str) -> bool:
        if self.is_excluded_url(url):
            logger.info("[skip] Excluded URL pattern: %s", url[:80])
            return False
        if not self.is_valid_job_url(url):
            logger.info("[skip] Not a job posting URL: %s", url[:80])
            return False
        if self.is_stale_posting(title, snippet):
            logger.info("[skip] Stale/closed posting: %s", title[:60])
            return False
        return True


@dataclass
class JobAccumulator:
    config: dict
    seen_urls: set[str]
    results: list[JobPosting]
    title_filters: list[str]
    lock: threading.Lock = field(default_factory=threading.Lock)
    cached_candidate_urls: set[str] = field(default_factory=set)
    candidate_cache_updates: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.policy = JobPolicy(self.config)

    def add_job(
        self,
        jp: JobPosting,
        allow_excluded_urls: bool = False,
        cache_candidate: bool = False,
    ) -> bool:
        url = jp.url
        if not url:
            return False

        canonical_url = canonicalize_url(url)
        if cache_candidate and self._is_cached_candidate(canonical_url, url):
            return False

        if not allow_excluded_urls and self.policy.is_excluded_url(url):
            logger.info("[skip] Excluded URL pattern: %s", url[:80])
            return False
        if not self.policy.is_valid_job_url(url):
            logger.info("[skip] Not a job posting URL: %s", url[:80])
            return False
        if not self.policy.accepts_job_content(jp.model_dump(), self.title_filters):
            return False

        with self.lock:
            if canonical_url in self.seen_urls:
                return False
            self.seen_urls.add(canonical_url)
            self.results.append(jp)

        logger.info(
            "[found] %s @ %s [%s]",
            jp.title[:50],
            jp.company or "?",
            jp.source or "?",
        )
        return True

    def _is_cached_candidate(self, canonical_url: str, url: str) -> bool:
        with self.lock:
            if canonical_url in self.cached_candidate_urls:
                logger.info("[skip] Cached discovery candidate: %s", url[:80])
                return True
            self.candidate_cache_updates.add(canonical_url)
        return False
