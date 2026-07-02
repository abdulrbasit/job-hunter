"""Arbeitnow job-board adapter."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.constants import JOB_BOARD_SNIPPET_CHARS
from job_hunter.core.utils import strip_html, title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import (
    DEFAULT_SINGLE_PAGE_SOURCE_CAP,
    pages_for_max_results,
    source_page_cap,
    source_page_delay,
)

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
_ARBEITNOW_PAGE_SIZE = 100
_TIMEOUT = get_timeout("job_boards")
logger = logging.getLogger(__name__)


def _parse_arbeitnow_date(value: int | float | str | None) -> str:
    """Return YYYY-MM-DD from a Unix timestamp or ISO string."""
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

    def is_enabled(self, api_config: dict) -> bool:
        config = (api_config or {}).get("http", {}).get("job_boards", {}).get("arbeitnow", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        config = get_api_config().get("http", {}).get("job_boards", {}).get("arbeitnow", {}) or {}
        if not config.get("enabled", True):
            return []

        max_pages = pages_for_max_results(
            params.max_results,
            _ARBEITNOW_PAGE_SIZE,
            base_cap=source_page_cap(DEFAULT_SINGLE_PAGE_SOURCE_CAP),
        )
        page_delay = source_page_delay()
        logger.info("[arbeitnow] [%s] location=%r, max_pages=%s", params.region_key, params.location, max_pages)
        jobs: list[JobPosting] = []
        for page in range(1, max_pages + 1):
            try:
                response = requests.get(ARBEITNOW_URL, params={"page": page}, timeout=_TIMEOUT)
                if response.status_code == 429:
                    logger.warning("[arbeitnow] page %s: rate limited; stopping for this run", page)
                    break
                response.raise_for_status()
                data = response.json().get("data", [])
            except Exception as exc:
                logger.warning("[arbeitnow] page %s: %s", page, exc)
                break
            if not data:
                break

            for job in data:
                title = job.get("title", "")
                if not title_is_allowed(title, params.job_titles, params.excluded_title_terms):
                    continue
                location = job.get("location", "")
                description = strip_html(job.get("description", ""))
                jobs.append(
                    JobPosting(
                        title=title,
                        company=job.get("company_name", ""),
                        url=job.get("url", ""),
                        posted_date_text=_parse_arbeitnow_date(job.get("created_at")),
                        location=location,
                        location_restrictions=[location] if location else [],
                        snippet=f"{location} — {description[:JOB_BOARD_SNIPPET_CHARS]}"
                        if location
                        else description[:JOB_BOARD_SNIPPET_CHARS],
                        source="Arbeitnow",
                        search_query=f"feed @ {params.region_key}",
                        region=params.region_key,
                    )
                )
            if page_delay and page < max_pages:
                time.sleep(page_delay)

        logger.info("[arbeitnow] %s matching jobs", len(jobs))
        return jobs
