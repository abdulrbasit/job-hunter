"""JSearch (RapidAPI) job-board adapter."""

from __future__ import annotations

import logging
import threading

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.config.secrets import RAPIDAPI_KEY
from job_hunter.constants import JOB_BOARD_SNIPPET_CHARS, MAX_SAFE_PAGES_PER_SOURCE
from job_hunter.core.api_budget import is_api_quota_exhausted, mark_api_exhausted, reserve_api_call
from job_hunter.core.utils import location_matches, title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._dates import truncate_date_text
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import pages_for_max_results

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"
_JSEARCH_PAGE_SIZE = 10
_TIMEOUT = get_timeout("job_boards")
_JSEARCH_FAILURES = 0
_JSEARCH_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


def _reset_jsearch_failures() -> None:
    global _JSEARCH_FAILURES
    with _JSEARCH_LOCK:
        _JSEARCH_FAILURES = 0


def _record_jsearch_failure() -> None:
    global _JSEARCH_FAILURES
    with _JSEARCH_LOCK:
        _JSEARCH_FAILURES += 1


def _jsearch_max_consecutive_failures() -> int:
    config = get_api_config().get("http", {}).get("job_boards", {})
    try:
        return int(config.get("max_consecutive_failures", 3))
    except (TypeError, ValueError):
        return 3


def _jsearch_suppressed(threshold: int | None = None) -> bool:
    max_failures = threshold if threshold is not None else _jsearch_max_consecutive_failures()
    if max_failures <= 0 or _JSEARCH_FAILURES < max_failures:
        return False
    logger.warning("[jsearch] skipped after %s consecutive failure(s)", _JSEARCH_FAILURES)
    return True


def _parse_job(job: dict, params: SearchParams, title: str) -> JobPosting | None:
    job_title = job.get("job_title", "")
    if not title_is_allowed(job_title, params.job_titles, params.excluded_title_terms):
        return None

    city = job.get("job_city") or ""
    country = job.get("job_country") or ""
    location = f"{city}, {country}".strip(", ")
    if params.location and (city or country):
        if not location_matches(city, params.location) and not location_matches(location, params.location):
            return None

    description = (job.get("job_description") or "")[:JOB_BOARD_SNIPPET_CHARS]
    return JobPosting(
        title=job_title,
        company=job.get("employer_name", ""),
        url=job.get("job_apply_link", ""),
        posted_date_text=truncate_date_text(job.get("job_posted_at_datetime_utc")),
        location=location,
        snippet=f"{location} — {description}" if location else description,
        source="JSearch",
        search_query=f"{title} @ {params.region_key}",
        region=params.region_key,
    )


def _request_params(query: str, page: int, params: SearchParams) -> dict[str, str]:
    request = {"query": query, "page": str(page), "num_pages": "1"}
    if params.country:
        request["country"] = params.country.lower()
    if params.search_lang:
        request["language"] = params.search_lang
    return request


class JSearchSource(JobSourceAdapter):
    tier = "api"

    def __init__(self) -> None:
        self._rapidapi_key: str = RAPIDAPI_KEY

    @property
    def source_name(self) -> str:
        return "jsearch"

    def is_enabled(self, api_config: dict) -> bool:
        return bool(self._rapidapi_key)

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        global _JSEARCH_FAILURES
        if not self._rapidapi_key:
            logger.warning("[jsearch] No RAPIDAPI_KEY configured — skipping")
            return []
        if not params.job_titles:
            logger.warning("[jsearch] No configured job titles; skipping")
            return []

        config = get_api_config().get("http", {}).get("job_boards", {}).get("jsearch", {}) or {}
        if not config.get("enabled", True) or _jsearch_suppressed():
            return []

        configured_pages = max(1, min(int(config.get("num_pages", 1)), MAX_SAFE_PAGES_PER_SOURCE))
        num_pages = pages_for_max_results(params.max_results, _JSEARCH_PAGE_SIZE, base_cap=configured_pages)
        headers = {"X-RapidAPI-Key": self._rapidapi_key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
        jobs: list[JobPosting] = []
        exclusions = " ".join(f'-"{term}"' for term in (params.excluded_title_terms or []))

        for title in params.job_titles:
            base_query = f"{title} in {params.location}" if params.location else title
            query = f"{base_query} {exclusions}".strip() if exclusions else base_query
            for page in range(1, num_pages + 1):
                logger.info("[jsearch] page=%d/%d query=%r", page, num_pages, query)
                request_params = _request_params(query, page, params)
                if not reserve_api_call("jsearch"):
                    return jobs

                try:
                    response = requests.get(
                        JSEARCH_URL,
                        headers=headers,
                        params=request_params,
                        timeout=_TIMEOUT,
                    )
                    response.raise_for_status()
                    data = response.json().get("data", [])
                    _reset_jsearch_failures()
                except Exception as exc:
                    if is_api_quota_exhausted(exc):
                        mark_api_exhausted("jsearch", exc=exc)
                        return jobs
                    _record_jsearch_failure()
                    logger.warning(
                        "[jsearch] query=%r page=%s: %s (failure %s/%s)",
                        query,
                        page,
                        exc,
                        _JSEARCH_FAILURES,
                        _jsearch_max_consecutive_failures(),
                    )
                    break

                jobs.extend(posting for job in data if (posting := _parse_job(job, params, title)) is not None)

        logger.info("[jsearch] %s jobs returned", len(jobs))
        return jobs
