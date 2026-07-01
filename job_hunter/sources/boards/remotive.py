"""Free Remotive remote jobs API source."""

from __future__ import annotations

import logging

from job_hunter.core.utils import strip_html, title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._dates import truncate_date_text
from job_hunter.sources._http import fetch_title_pages
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import (
    DEFAULT_SINGLE_PAGE_SOURCE_CAP,
    job_board_enabled,
    job_board_timeout,
    pages_for_max_results,
    source_page_cap,
)

logger = logging.getLogger(__name__)

_API_URL = "https://remotive.com/api/remote-jobs"
_PAGE_SIZE = 100


class RemotiveSource(JobSourceAdapter):
    global_feed = True

    @property
    def source_name(self) -> str:
        return "remotive"

    def is_enabled(self, api_config: dict) -> bool:
        return job_board_enabled("remotive")

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch remote jobs from Remotive's free public API."""
        if not job_board_enabled("remotive"):
            return []

        timeout = job_board_timeout("remotive")
        max_pages = pages_for_max_results(
            params.max_results, _PAGE_SIZE, base_cap=source_page_cap(DEFAULT_SINGLE_PAGE_SOURCE_CAP)
        )
        jobs: list[JobPosting] = []

        for title, raw_jobs in fetch_title_pages(
            _API_URL,
            params.job_titles,
            lambda t, p: {"search": t, "limit": _PAGE_SIZE, "page": p},
            "jobs",
            timeout=timeout,
            max_pages=max_pages,
            source_name="remotive",
        ):
            before = len(jobs)
            for item in raw_jobs:
                job_title = str(item.get("title") or "")
                job_location = str(item.get("candidate_required_location") or "Remote")
                if not title_is_allowed(job_title, params.job_titles, params.excluded_title_terms):
                    continue
                description = strip_html(item.get("description") or "")
                jobs.append(
                    JobPosting(
                        title=job_title,
                        company=str(item.get("company_name") or ""),
                        url=str(item.get("url") or ""),
                        posted_date_text=truncate_date_text(item.get("publication_date")),
                        location=job_location,
                        snippet=description[:3000],
                        source="Remotive",
                        search_query=f"{title} @ {params.region_key}",
                        region=params.region_key,
                        location_restrictions=[job_location] if job_location else [],
                        employment_type=str(item.get("job_type") or ""),
                    )
                )
            logger.info("[remotive] +%d jobs for %r in %s", len(jobs) - before, title, params.region_key)

        return jobs
