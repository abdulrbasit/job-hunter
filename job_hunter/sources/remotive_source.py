"""Free Remotive remote jobs API source."""

from __future__ import annotations

import logging

from job_hunter.config.loader import get_timeout, load_api_config
from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources._http import fetch_title_pages
from job_hunter.sources.source_config import DEFAULT_SINGLE_PAGE_SOURCE_CAP, source_page_cap

logger = logging.getLogger(__name__)

_API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(JobSourceAdapter):
    global_feed = True

    @property
    def source_name(self) -> str:
        return "remotive"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("remotive", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch remote jobs from Remotive's free public API."""
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("remotive", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap(DEFAULT_SINGLE_PAGE_SOURCE_CAP)
        jobs: list[JobPosting] = []

        for title, raw_jobs in fetch_title_pages(
            _API_URL,
            params.job_titles,
            lambda t, p: {"search": t, "limit": 100, "page": p},
            "jobs",
            timeout=timeout,
            max_pages=max_pages,
            source_name="remotive",
        ):
            before = len(jobs)
            for item in raw_jobs:
                job_title = str(item.get("title") or "")
                job_location = str(item.get("candidate_required_location") or "Remote")
                if not title_matches(job_title, params.job_titles, []):
                    continue
                description = strip_html(item.get("description") or "")
                jobs.append(
                    JobPosting(
                        title=job_title,
                        company=str(item.get("company_name") or ""),
                        url=str(item.get("url") or ""),
                        posted=str(item.get("publication_date") or "")[:10],
                        location=job_location,
                        snippet=description[:3000],
                        source="Remotive",
                        query=f"{title} @ {params.region_key}",
                        region=params.region_key,
                    )
                )
            logger.info("[remotive] +%d jobs for %r in %s", len(jobs) - before, title, params.region_key)

        return jobs
