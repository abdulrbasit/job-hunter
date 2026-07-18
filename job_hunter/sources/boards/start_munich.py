"""Bounded public Start Munich/Getro job-board adapter."""

from __future__ import annotations

import requests

from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.boards._startup_html import parse_startup_jobs
from job_hunter.sources.source_config import job_board_enabled, job_board_timeout

_URL = "https://jobs.startmunich.de/jobs"


class StartMunichSource(JobSourceAdapter):
    supported_countries = frozenset({"DE"})
    startup_source = True

    @property
    def source_name(self) -> str:
        return "start_munich"

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        if not self.supports_country(params.country) or not job_board_enabled(self.source_name):
            return []
        response = requests.get(_URL, timeout=job_board_timeout(self.source_name))
        response.raise_for_status()
        return parse_startup_jobs(response.text, _URL, "Start Munich", params)
