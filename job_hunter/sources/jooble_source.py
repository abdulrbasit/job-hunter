"""Jooble job aggregator source — free API key required.

Register for a free key at https://jooble.org/api/about
POST-based paged search with keyword + location.

Required env var (optional — source skips silently if absent):
  JOOBLE_API_KEY — API key from jooble.org
"""

from __future__ import annotations

import logging

import requests

from job_hunter.config.loader import JOOBLE_API_KEY, get_timeout, load_api_config
from job_hunter.core.api_budget import (
    is_api_quota_exhausted,
    mark_api_exhausted,
    reserve_api_call,
)
from job_hunter.core.utils import title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import (
    DEFAULT_PAGED_SOURCE_CAP,
    source_page_cap,
    terminal_http_status,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://jooble.org/api/{api_key}"


class JoobleSource(JobSourceAdapter):
    tier = "api"

    def __init__(self) -> None:
        self._api_key: str = JOOBLE_API_KEY

    @property
    def source_name(self) -> str:
        return "jooble"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jooble", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from Jooble for each title × region. Returns [] silently if key is missing."""
        if not self._api_key:
            logger.warning("[jooble] JOOBLE_API_KEY not set — skipping")
            return []

        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jooble", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap(DEFAULT_PAGED_SOURCE_CAP)
        location = params.location

        url = _BASE_URL.format(api_key=self._api_key)
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            logger.info("[jooble] [%s] Searching for %r", params.region_key, title)

            for page in range(1, max_pages + 1):
                if not reserve_api_call("jooble"):
                    return jobs

                try:
                    resp = requests.post(
                        url,
                        json={"keywords": title, "location": location, "page": page},
                        timeout=timeout,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    if is_api_quota_exhausted(exc):
                        mark_api_exhausted("jooble", exc=exc)
                        return jobs
                    if terminal_http_status(exc):
                        logger.warning("[jooble] stopping after terminal HTTP error: %s", exc)
                        return jobs
                    logger.warning(
                        "[jooble] request failed for %r in %r page %s: %s",
                        title,
                        params.region_key,
                        page,
                        exc,
                    )
                    break

                raw_jobs = data.get("jobs") if isinstance(data, dict) else None
                if not raw_jobs:
                    break

                before = len(jobs)
                for item in raw_jobs:
                    if not isinstance(item, dict):
                        continue
                    job_title = str(item.get("title") or "")
                    if not title_matches(job_title, params.job_titles, []):
                        continue
                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=str(item.get("company") or ""),
                            url=str(item.get("link") or ""),
                            posted=str(item.get("updated") or "")[:10],
                            location=str(item.get("location") or ""),
                            snippet=str(item.get("snippet") or "")[:3000],
                            source="Jooble",
                            query=f"{title} @ {params.region_key}",
                            region=params.region_key,
                        )
                    )
                logger.info(
                    "[jooble] +%d jobs for %r in %r page %s",
                    len(jobs) - before,
                    title,
                    params.region_key,
                    page,
                )

        logger.info("[jooble] Complete: %d total jobs found", len(jobs))
        return jobs
