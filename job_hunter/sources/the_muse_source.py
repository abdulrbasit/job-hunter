"""Free The Muse jobs API source."""

from __future__ import annotations

import logging

import requests

from job_hunter.core.config import get_timeout, load_api_config
from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import DEFAULT_SINGLE_PAGE_SOURCE_CAP, source_page_cap

logger = logging.getLogger(__name__)

_API_URL = "https://www.themuse.com/api/public/jobs"


class TheMuseSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "the_muse"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("the_muse", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from The Muse's free public API."""
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("the_muse", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap(DEFAULT_SINGLE_PAGE_SOURCE_CAP)
        location = params.location
        jobs: list[JobPosting] = []

        query_label = ", ".join(params.job_titles)
        for page in range(0, max_pages):
            try:
                resp = requests.get(
                    _API_URL,
                    params={"page": page, "descending": "true"},
                    timeout=timeout,
                )
                resp.raise_for_status()
                raw_jobs = resp.json().get("results", [])
            except Exception as exc:
                logger.warning(
                    "[the-muse] failed for %r in %s page %s: %s",
                    query_label,
                    params.region_key,
                    page,
                    exc,
                )
                break

            if not raw_jobs:
                break

            before = len(jobs)
            for item in raw_jobs:
                job_title = str(item.get("name") or "")
                job_location_list = item.get("locations") or []
                job_location = (
                    ", ".join(str(loc.get("name") or "") for loc in job_location_list if isinstance(loc, dict))
                    or "Remote"
                )
                if not title_matches(job_title, params.job_titles, []):
                    continue
                if location and job_location != "Remote":
                    if not location_matches(job_location, location):
                        continue
                description = strip_html(item.get("contents") or "")
                company_name = str((item.get("company") or {}).get("name") or "")
                job_url = str(item.get("refs", {}).get("landing_page") or "")
                posted = str(item.get("publication_date") or "")[:10]
                jobs.append(
                    JobPosting(
                        title=job_title,
                        company=company_name,
                        url=job_url,
                        posted=posted,
                        location=job_location,
                        snippet=description[:3000],
                        source="The Muse",
                        query=f"{query_label} @ {params.region_key}",
                        region=params.region_key,
                    )
                )
            logger.info(
                "[the-muse] +%d jobs for %r in %s",
                len(jobs) - before,
                query_label,
                params.region_key,
            )

        return jobs
