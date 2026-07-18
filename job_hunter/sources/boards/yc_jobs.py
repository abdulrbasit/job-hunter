"""Bounded public Y Combinator jobs adapter."""

from __future__ import annotations

import requests

from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.boards._startup_html import parse_startup_jobs
from job_hunter.sources.source_config import job_board_enabled, job_board_timeout

_URL = "https://www.ycombinator.com/jobs"


class YCJobsSource(JobSourceAdapter):
    startup_source = True
    once_per_run = True

    @property
    def source_name(self) -> str:
        return "yc_jobs"

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        if not job_board_enabled(self.source_name):
            return []
        response = requests.get(_URL, timeout=job_board_timeout(self.source_name))
        response.raise_for_status()
        return parse_startup_jobs(response.text, _URL, "Y Combinator Jobs", params)
