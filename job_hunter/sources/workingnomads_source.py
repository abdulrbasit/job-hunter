"""Working Nomads remote job board — no API key required.

Public REST endpoint returns all current remote jobs as a JSON list.
No geographic restriction; fires for all enabled regions.
"""

from __future__ import annotations

import logging

import requests

from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import job_board_enabled, job_board_timeout

logger = logging.getLogger(__name__)

_API_URL = "https://www.workingnomads.com/api/exposed_jobs/"


class WorkingNomadsSource(JobSourceAdapter):
    global_feed = True

    @property
    def source_name(self) -> str:
        return "workingnomads"

    def is_enabled(self, api_cfg: dict) -> bool:
        return job_board_enabled("workingnomads")

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
            if not title_matches(job_title, params.job_titles, []):
                continue
            jobs.append(
                JobPosting(
                    title=job_title,
                    company=str(item.get("company_name") or ""),
                    url=str(item.get("url") or ""),
                    posted=str(item.get("pub_date") or "")[:10],
                    location=str(item.get("region") or "Remote"),
                    snippet=strip_html(str(item.get("description") or ""))[:3000],
                    source="WorkingNomads",
                    query=f"{' | '.join(params.job_titles[:3])} @ {params.region_key}",
                    region=params.region_key,
                )
            )

        logger.info("[workingnomads] Complete: %d jobs matched title filters", len(jobs))
        return jobs
