"""Bounded Startup.jobs RSS adapter with required canonical attribution."""

from __future__ import annotations

import requests
from defusedxml import ElementTree

from job_hunter.core.utils import strip_html, title_is_allowed
from job_hunter.models import CompanyType, JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import job_board_enabled, job_board_timeout

_URL = "https://startup.jobs/feeds/jobs"


class StartupJobsSource(JobSourceAdapter):
    startup_source = True
    once_per_run = True

    @property
    def source_name(self) -> str:
        return "startup_jobs"

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        if not job_board_enabled(self.source_name):
            return []
        response = requests.get(_URL, timeout=job_board_timeout(self.source_name))
        response.raise_for_status()
        jobs: list[JobPosting] = []
        for item in ElementTree.fromstring(response.text).findall(".//item")[: params.max_results]:
            raw_title = (item.findtext("title") or "").strip()
            company = (item.findtext("author") or item.findtext("company") or "").strip()
            title = raw_title
            if " at " in raw_title and not company:
                title, company = raw_title.rsplit(" at ", 1)
            if not title_is_allowed(title, params.job_titles, params.excluded_title_terms):
                continue
            jobs.append(
                JobPosting(
                    title=title,
                    company=company,
                    url=(item.findtext("link") or "").strip(),
                    snippet=strip_html(item.findtext("description") or "")[:3000],
                    location=(item.findtext("location") or "Remote").strip(),
                    source="Startup.jobs",
                    source_url=_URL,
                    region=params.region_key,
                    search_query=f"startup feed @ {params.region_key}",
                    company_type=CompanyType.STARTUP,
                )
            )
        return jobs
