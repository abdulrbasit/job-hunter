"""
Global job board scrapers: Arbeitnow and JSearch (RapidAPI).

These search across the whole market rather than targeting specific career pages,
so they complement the per-company ATS fetchers in sources/ats.py.

- Arbeitnow: free, no auth, Germany-focused REST API.
- JSearch:   RapidAPI aggregator (LinkedIn, Indeed, Glassdoor, etc.);
             free tier = 200 req/month; requires RAPIDAPI_KEY.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

import requests

from job_hunter.config.loader import RAPIDAPI_KEY, get_api_config, get_timeout
from job_hunter.constants import JOB_BOARD_SNIPPET_CHARS
from job_hunter.core.api_budget import (
    is_api_quota_exhausted,
    mark_api_exhausted,
    reserve_api_call,
)
from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import (
    DEFAULT_SINGLE_PAGE_SOURCE_CAP,
    source_page_cap,
    source_page_delay,
)

_TIMEOUT = get_timeout("job_boards")
_JSEARCH_FAILURES = 0


_JSEARCH_LOCK = threading.Lock()


def _reset_jsearch_failures() -> None:
    global _JSEARCH_FAILURES
    with _JSEARCH_LOCK:
        _JSEARCH_FAILURES = 0


def _record_jsearch_failure() -> None:
    global _JSEARCH_FAILURES
    with _JSEARCH_LOCK:
        _JSEARCH_FAILURES += 1


logger = logging.getLogger(__name__)

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"


def _jsearch_max_consecutive_failures() -> int:
    cfg = get_api_config().get("http", {}).get("job_boards", {})
    try:
        return int(cfg.get("max_consecutive_failures", 3))
    except (TypeError, ValueError):
        return 3


def _jsearch_suppressed(threshold: int | None = None) -> bool:
    max_failures = threshold if threshold is not None else _jsearch_max_consecutive_failures()
    if max_failures <= 0 or _JSEARCH_FAILURES < max_failures:
        return False

    logger.warning(
        "[jsearch] skipped after %s consecutive failure(s)",
        _JSEARCH_FAILURES,
    )
    return True


def _parse_arbeitnow_date(value: int | float | str | None) -> str:
    """Return YYYY-MM-DD from a Unix timestamp int or ISO string, or '' on failure."""
    if not value:
        return ""
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%d")
        return str(value)[:10]
    except Exception:
        return ""


class ArbeitnowSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "arbeitnow"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = get_api_config().get("http", {}).get("job_boards", {}).get("arbeitnow", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        boards_cfg = get_api_config().get("http", {}).get("job_boards", {}) or {}
        arbeitnow_cfg = boards_cfg.get("arbeitnow", {}) or {}
        if not arbeitnow_cfg.get("enabled", True):
            return []

        max_pages = source_page_cap(DEFAULT_SINGLE_PAGE_SOURCE_CAP)
        page_delay = source_page_delay()
        location_filter = params.location

        logger.info(
            "[arbeitnow] [%s] location=%r, max_pages=%s",
            params.region_key,
            location_filter,
            max_pages,
        )
        jobs: list[JobPosting] = []
        for page in range(1, max_pages + 1):
            try:
                resp = requests.get(ARBEITNOW_URL, params={"page": page}, timeout=_TIMEOUT)
                if resp.status_code == 429:
                    logger.warning(
                        "[arbeitnow] page %s: rate limited; stopping for this run",
                        page,
                    )
                    break
                resp.raise_for_status()
                data = resp.json().get("data", [])
            except Exception as e:
                logger.warning(f"[arbeitnow] page {page}: {e}")
                break

            if not data:
                break

            for job in data:
                title = job.get("title", "")
                location = job.get("location", "")

                if not title_matches(title, params.job_titles, []):
                    continue
                if not location_matches(location, location_filter):
                    continue

                description = strip_html(job.get("description", ""))
                jobs.append(
                    JobPosting(
                        title=title,
                        company=job.get("company_name", ""),
                        url=job.get("url", ""),
                        posted=_parse_arbeitnow_date(job.get("created_at")),
                        location=location,
                        snippet=f"{location} — {description[:JOB_BOARD_SNIPPET_CHARS]}"
                        if location
                        else description[:JOB_BOARD_SNIPPET_CHARS],
                        source="Arbeitnow",
                        query=f"feed @ {params.region_key}",
                        region=params.region_key,
                    )
                )
            if page_delay and page < max_pages:
                time.sleep(page_delay)

        logger.info(f"[arbeitnow] {len(jobs)} matching jobs")
        return jobs


class JSearchSource(JobSourceAdapter):
    tier = "api"

    def __init__(self) -> None:
        self._rapidapi_key: str = RAPIDAPI_KEY

    @property
    def source_name(self) -> str:
        return "jsearch"

    def is_enabled(self, api_cfg: dict) -> bool:
        return bool(self._rapidapi_key)

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        global _JSEARCH_FAILURES

        if not self._rapidapi_key:
            logger.warning("[jsearch] No RAPIDAPI_KEY configured — skipping")
            return []

        if not params.job_titles:
            logger.warning("[jsearch] No configured job titles; skipping")
            return []

        boards_cfg = get_api_config().get("http", {}).get("job_boards", {}) or {}
        jsearch_cfg = boards_cfg.get("jsearch", {}) or {}
        if not jsearch_cfg.get("enabled", True):
            return []

        if _jsearch_suppressed():
            return []

        num_pages = int(jsearch_cfg.get("num_pages", 1))
        location_filter = params.location
        country = params.country
        language = params.search_lang

        headers = {
            "X-RapidAPI-Key": self._rapidapi_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        jobs: list[JobPosting] = []

        exclusions = " ".join(f'-"{term}"' for term in (params.excluded_title_terms or []))
        for title in params.job_titles:
            base_query = f"{title} in {location_filter}" if location_filter else title
            query = f"{base_query} {exclusions}".strip() if exclusions else base_query

            for page in range(1, num_pages + 1):
                req_params: dict = {
                    "query": query,
                    "page": str(page),
                    "num_pages": "1",
                }
                if country:
                    req_params["country"] = country.lower()
                if language:
                    req_params["language"] = language

                if not reserve_api_call("jsearch"):
                    return jobs

                try:
                    resp = requests.get(
                        JSEARCH_URL,
                        headers=headers,
                        params=req_params,
                        timeout=_TIMEOUT,
                    )
                    resp.raise_for_status()
                    data = resp.json().get("data", [])
                    _reset_jsearch_failures()
                except Exception as e:
                    if is_api_quota_exhausted(e):
                        mark_api_exhausted("jsearch", exc=e)
                        return jobs
                    _record_jsearch_failure()
                    max_failures = _jsearch_max_consecutive_failures()
                    logger.warning(
                        "[jsearch] query=%r page=%s: %s (failure %s/%s)",
                        query,
                        page,
                        e,
                        _JSEARCH_FAILURES,
                        max_failures,
                    )
                    break

                for job in data:
                    job_title = job.get("job_title", "")
                    if not title_matches(job_title, params.job_titles, []):
                        continue

                    city = job.get("job_city") or ""
                    job_country = job.get("job_country") or ""
                    location_str = f"{city}, {job_country}".strip(", ")

                    if location_filter and (city or job_country):
                        if not location_matches(city, location_filter) and not location_matches(
                            location_str, location_filter
                        ):
                            continue

                    description = (job.get("job_description") or "")[:JOB_BOARD_SNIPPET_CHARS]
                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=job.get("employer_name", ""),
                            url=job.get("job_apply_link", ""),
                            posted=(job.get("job_posted_at_datetime_utc") or "")[:10],
                            location=location_str,
                            snippet=f"{location_str} — {description}" if location_str else description,
                            source="JSearch",
                            query=f"{title} @ {params.region_key}",
                            region=params.region_key,
                        )
                    )

        logger.info(f"[jsearch] {len(jobs)} jobs returned")
        return jobs
