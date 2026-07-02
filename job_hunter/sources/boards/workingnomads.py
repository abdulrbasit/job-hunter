"""Working Nomads remote job board — no API key required.

Public REST endpoint returns all current remote jobs as a JSON list.
No geographic restriction; fires for all enabled regions.
"""

from __future__ import annotations

import logging

import requests

from job_hunter.core.utils import strip_html, title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._dates import truncate_date_text
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import job_board_enabled, job_board_timeout

logger = logging.getLogger(__name__)

_API_URL = "https://www.workingnomads.com/api/exposed_jobs/"


class WorkingNomadsSource(JobSourceAdapter):
    global_feed = True

    @property
    def source_name(self) -> str:
        return "workingnomads"

    def is_enabled(self, api_config: dict) -> bool:
        config = (api_config or {}).get("http", {}).get("job_boards", {}).get("workingnomads", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch remote jobs from Working Nomads public API."""
        if not job_board_enabled("workingnomads"):
            return []

        timeout = job_board_timeout("workingnomads")

        logger.info("[workingnomads] Fetching all remote jobs")
        try:
            resp = requests.get(_API_URL, timeout=timeout)
            resp.raise_for_status()
            raw_jobs = resp.json()
        except Exception as exc:
            logger.warning("[workingnomads] request failed: %s", exc)
            return []

        if not isinstance(raw_jobs, list):
            logger.warning("[workingnomads] unexpected response type: %s", type(raw_jobs))
            return []

        jobs: list[JobPosting] = []
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue
            job_title = str(item.get("title") or "")
            if not title_is_allowed(job_title, params.job_titles, params.excluded_title_terms):
                continue
            jobs.append(
                JobPosting(
                    title=job_title,
                    company=str(item.get("company_name") or ""),
                    url=str(item.get("url") or ""),
                    posted_date_text=truncate_date_text(item.get("pub_date")),
                    location=str(item.get("region") or "Remote"),
                    snippet=strip_html(str(item.get("description") or ""))[:3000],
                    source="WorkingNomads",
                    search_query=f"{' | '.join(params.job_titles[:3])} @ {params.region_key}",
                    region=params.region_key,
                    location_restrictions=[str(item.get("region") or "")] if item.get("region") else [],
                )
            )

        logger.info("[workingnomads] Complete: %d jobs matched title filters", len(jobs))
        return jobs
