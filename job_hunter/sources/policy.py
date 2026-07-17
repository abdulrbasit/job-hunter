"""Filtering and dedupe policy for discovered job postings."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from job_hunter.config.reference_data import resolve_title_exclusions
from job_hunter.core.builtin_filters import (
    CONTRACT_PHRASES,
    EXCLUDED_LISTING_URL_PATTERNS,
    LISTING_ONLY_PATHS,
    MAX_POSTING_AGE_DAYS,
    RESTRICTION_PHRASES,
    STALE_INDICATORS,
    US_ONLY_PHRASES,
)
from job_hunter.core.language import detect_language
from job_hunter.core.utils import title_is_allowed
from job_hunter.filters import FilterSet
from job_hunter.locations import COUNTRY_NAME_TO_CODE
from job_hunter.models import JobPosting
from job_hunter.sources.search import canonicalize_url

logger = logging.getLogger(__name__)
_COUNTRY_ALIAS_TO_CODE: dict[str, str] = {
    **COUNTRY_NAME_TO_CODE,
    "uk": "GB",
    "u k": "GB",
}
_SHORT_COUNTRY_CODES: frozenset[str] = frozenset(COUNTRY_NAME_TO_CODE.values())
# Precompiled once — is_location_restricted() runs this per job screened, so compiling
# a bare-country-name pattern per country per call (~230 countries) would be wasteful.
_COUNTRY_NAME_PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(r"\b" + re.escape(name) + r"\b") for name in COUNTRY_NAME_TO_CODE
}

_BROAD_LOCATION_RESTRICTIONS: frozenset[str] = frozenset(
    {
        "anywhere",
        "anywhere in the world",
        "global",
        "remote",
        "worldwide",
        "world wide",
    }
)

_EUROPE_COUNTRY_CODES: frozenset[str] = frozenset(
    {
        "AL",
        "AT",
        "BA",
        "BE",
        "BG",
        "BY",
        "CH",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GB",
        "GR",
        "HR",
        "HU",
        "IE",
        "IS",
        "IT",
        "LT",
        "LU",
        "LV",
        "MD",
        "MK",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "RS",
        "SE",
        "SI",
        "SK",
        "UA",
    }
)

_MIDDLE_EAST_COUNTRY_CODES: frozenset[str] = frozenset({"AE", "SA", "QA", "KW", "BH", "OM"})

_EUROPE_LOCATION_RESTRICTIONS: frozenset[str] = frozenset({"eu", "europe"})
_MIDDLE_EAST_LOCATION_RESTRICTIONS: frozenset[str] = frozenset({"middle east", "gcc", "mena", "gulf"})
# EMEA spans Europe + Middle East (+ Africa, untracked) — broader than "europe" alone.
_EMEA_LOCATION_RESTRICTIONS: frozenset[str] = frozenset({"emea"})
_REMOTE_ONLY_LOCATIONS: frozenset[str] = frozenset({"", "remote"})

_EMPLOYMENT_TYPE_CANONICAL: dict[str, str] = {
    "full_time": "full_time",
    "full-time": "full_time",
    "fulltime": "full_time",
    "full time": "full_time",
    "permanent": "full_time",
    "employee": "full_time",
    "part_time": "part_time",
    "part-time": "part_time",
    "parttime": "part_time",
    "part time": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "freelance": "contract",
    "freelancer": "contract",
    "temporary": "temporary",
    "temp": "temporary",
    "casual": "temporary",
    "seasonal": "temporary",
    "apprenticeship": "temporary",
    "internship": "internship",
    "intern": "internship",
    "werkstudent": "internship",
    "werkstudentin": "internship",
}


def normalize_employment_type(val: str) -> str:
    """Map raw employment-type strings to canonical values (full_time/part_time/contract/temporary/internship)."""
    if not val:
        return ""
    key = re.sub(r"[-\s]+", "_", val.lower().strip())
    return _EMPLOYMENT_TYPE_CANONICAL.get(key, key)


def derive_country_code(location: str) -> str:
    """Return best-guess ISO alpha-2 country code from raw location string. Empty if none found."""
    codes = _codes_from_location_text(location)
    return next(iter(codes), "")


def _norm_location_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _codes_from_location_text(value: object) -> set[str]:
    text = _norm_location_text(value)
    if not text:
        return set()
    if text.upper() in _SHORT_COUNTRY_CODES:
        return {text.upper()}
    codes: set[str] = set()
    for name, code in sorted(_COUNTRY_ALIAS_TO_CODE.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = _norm_location_text(name)
        if normalized and re.search(r"\b" + re.escape(normalized) + r"\b", text):
            codes.add(code)
    return codes


def _restricted_codes_from_slug_text(value: object) -> set[str]:
    text = _norm_location_text(value)
    codes: set[str] = set()
    short_aliases = {"us": "US", "usa": "US", "uk": "GB", "gb": "GB", "ca": "CA"}
    for alias, code in short_aliases.items():
        patterns = (
            f"remote {alias}",
            f"{alias} remote",
            f"{alias} only",
            f"only {alias}",
            f"within the {alias}",
        )
        if any(re.search(r"\b" + re.escape(pattern) + r"\b", text) for pattern in patterns):
            codes.add(code)
    for name, code in sorted(COUNTRY_NAME_TO_CODE.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = _norm_location_text(name)
        patterns = (
            f"remote {normalized}",
            f"{normalized} remote",
            f"{normalized} only",
            f"only {normalized}",
            f"within the {normalized}",
        )
        if any(re.search(r"\b" + re.escape(pattern) + r"\b", text) for pattern in patterns):
            codes.add(code)
    return codes


def _is_broad_location_restriction(value: object, allowed_codes: set[str]) -> bool:
    text = _norm_location_text(value)
    if text in _BROAD_LOCATION_RESTRICTIONS:
        return True
    if text in _EUROPE_LOCATION_RESTRICTIONS:
        return bool(allowed_codes & _EUROPE_COUNTRY_CODES)
    if text in _MIDDLE_EAST_LOCATION_RESTRICTIONS:
        return bool(allowed_codes & _MIDDLE_EAST_COUNTRY_CODES)
    if text in _EMEA_LOCATION_RESTRICTIONS:
        return bool(allowed_codes & (_EUROPE_COUNTRY_CODES | _MIDDLE_EAST_COUNTRY_CODES))
    return False


def _looks_like_remote_city_region(region_config: dict) -> bool:
    locations = region_config.get("locations") or []
    if isinstance(locations, str):
        locations = [locations]
    location = _norm_location_text(region_config.get("location") or " ".join(str(item) for item in locations))
    return "remote" in location or location in _BROAD_LOCATION_RESTRICTIONS


@dataclass(frozen=True)
class JobPolicy:
    config: dict
    filters: FilterSet | None = None

    def __post_init__(self) -> None:
        if self.filters is None:
            object.__setattr__(self, "filters", FilterSet.from_config(self.config))

    @property
    def excluded_title_terms(self) -> list[str]:
        return resolve_title_exclusions(self.config)

    @property
    def excluded_companies(self) -> list[str]:
        return self.filters.values("excluded_companies") if self.filters else []

    @property
    def excluded_industries(self) -> list[str]:
        return self.filters.values("excluded_industries") if self.filters else []

    def is_valid_job_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")

        if not path:
            return False
        if path in LISTING_ONLY_PATHS:
            return False

        segments = [s for s in path.split("/") if s]
        return len(segments) >= 2

    def is_excluded_url(self, url: str) -> bool:
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in EXCLUDED_LISTING_URL_PATTERNS)

    def is_stale_posting(self, title: str, snippet: str) -> bool:
        combined = (title + " " + snippet).lower()
        return any(indicator in combined for indicator in STALE_INDICATORS)

    def is_excluded_company(self, company: str) -> bool:
        return bool(self.filters and self.filters.matches("excluded_companies", company))

    def is_excluded_industry(self, snippet: str) -> bool:
        return bool(self.filters and self.filters.matches("excluded_industries", snippet))

    def is_contract_posting(self, job: dict) -> bool:
        """True for fixed-term/contract postings — checks the structured employment_type
        field first (reliable, ATS-sourced), falling back to snippet phrase matching for
        sources that don't populate it."""
        employment_type = str(job.get("employment_type") or "").strip().lower()
        if "contract" in employment_type:
            return True
        snippet = str(job.get("snippet") or "").lower()
        return any(phrase in snippet for phrase in CONTRACT_PHRASES)

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
        if title_filters and not title_is_allowed(title, title_filters, self.excluded_title_terms):
            logger.info("[skip] Title not in filters: %s", title[:60])
            return "excluded_title"
        if self.is_excluded_company(company):
            logger.info("[skip] Excluded company: %s", company[:60])
            return "excluded_company"
        if self.is_stale_posting(title, snippet):
            logger.info("[skip] Stale/closed posting: %s", title[:60])
            return "stale_content"
        if self.is_contract_posting(job):
            logger.info("[skip] Contract/fixed-term posting: %s", title[:60])
            return "contract_role"
        date_status = self.posting_date_status(str(job.get("posted_date_text") or ""))
        if date_status not in {"current", "missing"}:
            logger.info("[skip] %s: %s", date_status, title[:60])
            return date_status
        return ""

    def _region_locations(self, region_config: dict) -> list[str]:
        locations = region_config.get("locations") or []
        if isinstance(locations, str):
            locations = [locations]
        if not locations and region_config.get("location"):
            locations = [region_config.get("location")]
        return [str(location) for location in locations if str(location or "").strip()]

    def has_wrong_location(self, job: dict, region_config: dict) -> bool:
        """Return True if job location doesn't match any allowed location in region_config."""
        if self.location_metadata_matches_region(job, region_config):
            return False
        allowed = self._region_locations(region_config)
        if not allowed:
            return False
        job_location = str(job.get("location") or "")
        if not job_location:
            return False
        from job_hunter.core.utils import location_matches

        return not any(location_matches(job_location, loc) for loc in allowed)

    def location_metadata_matches_region(self, job: dict, region_config: dict) -> bool:
        allowed_codes = {str(region_config.get("country") or "").strip().upper()}
        allowed_codes.discard("")
        restrictions = [str(value) for value in job.get("location_restrictions", []) or [] if str(value).strip()]
        if not restrictions or not allowed_codes:
            return False
        explicit_codes = set().union(*(_codes_from_location_text(value) for value in restrictions))
        if explicit_codes:
            return bool(explicit_codes & allowed_codes)
        return any(_is_broad_location_restriction(value, allowed_codes) for value in restrictions)

    def has_incompatible_location_metadata(self, job: dict, region_config: dict) -> bool:
        allowed_codes = {str(region_config.get("country") or "").strip().upper()}
        allowed_codes.discard("")
        if not region_config or not allowed_codes:
            return False

        restrictions = [str(value) for value in job.get("location_restrictions", []) or [] if str(value).strip()]
        if restrictions:
            return not self.location_metadata_matches_region(job, region_config)

        combined = " ".join(str(job.get(key) or "") for key in ("url", "title", "snippet", "location"))
        mentioned_codes = _restricted_codes_from_slug_text(combined)
        if mentioned_codes and not mentioned_codes & allowed_codes:
            return True

        location = _norm_location_text(job.get("location"))
        if location in _REMOTE_ONLY_LOCATIONS and not _looks_like_remote_city_region(region_config):
            return True
        return False

    def has_incompatible_location_for_global_feed(self, job: dict) -> bool:
        """For global-feed jobs (no per-region context): reject if location data names only non-configured countries."""
        allowed_codes = self._allowed_country_codes()
        if not allowed_codes:
            return False
        restrictions = [str(v) for v in job.get("location_restrictions", []) or [] if str(v).strip()]
        if restrictions:
            explicit_codes = set().union(*(_codes_from_location_text(value) for value in restrictions))
            if explicit_codes:
                return not bool(explicit_codes & allowed_codes)
            return not any(_is_broad_location_restriction(v, allowed_codes) for v in restrictions)
        location = str(job.get("location") or "")
        if not location or _norm_location_text(location) in _REMOTE_ONLY_LOCATIONS:
            return False
        codes = _codes_from_location_text(location)
        return bool(codes) and not codes & allowed_codes

    def language_screen(self, title: str, description: str) -> tuple[bool, str | None, bool]:
        """Detect the posting's language and compare it against hunt_languages.

        Returns (excluded, detected_code, low_confidence). Fails open (excluded=False)
        when hunt_languages is unset or detection confidence is too low to trust —
        low_confidence signals the caller should flag the job for review, not exclude it.
        """
        allowed = set(self.filters.values("hunt_languages")) if self.filters else set()
        if not allowed:
            return False, None, False
        detection = detect_language(title, description)
        if detection.code is None:
            return False, None, True
        return detection.code not in allowed, detection.code, False

    def _allowed_country_codes(self) -> set[str]:
        from job_hunter.locations import enabled_locations

        canonical = {location.country for location in enabled_locations(self.config) if location.country}
        if canonical:
            return canonical
        regions = self.config.get("regions", {}) or {}
        codes: set[str] = set()
        for region_config in regions.values() if isinstance(regions, dict) else []:
            if isinstance(region_config, dict) and region_config.get("enabled", True):
                country = (region_config.get("country") or "").strip().upper()
                if country:
                    codes.add(country)
        return codes

    def is_location_restricted(self, title: str, snippet: str) -> bool:
        """Return True if JD text restricts work to a country not in user's configured regions."""
        allowed = self._allowed_country_codes()
        if not allowed:
            return False
        text = (title + " " + snippet).lower()
        title_lower = title.lower()
        for country_name, iso_code in COUNTRY_NAME_TO_CODE.items():
            if iso_code in allowed:
                continue
            for phrase in RESTRICTION_PHRASES:
                if phrase.format(country_name) in text:
                    return True
            # standalone country name in title catches "PM - Colombia", "PM (Remote/Egypt)"
            if _COUNTRY_NAME_PATTERNS[country_name].search(title_lower):
                return True
        # US/Canada shorthand phrases — "us" is too noisy for the country loop
        if "US" not in allowed and any(phrase in text for phrase in US_ONLY_PHRASES):
            return True
        return False

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
