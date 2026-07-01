"""RemoteOK job feed source — no key required.

Public JSON feed: https://remoteok.com/api
Returns all remote jobs; first element is metadata — skip it.
Filter locally by title and region location.
"""

from __future__ import annotations

import logging

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._dates import truncate_date_text
from job_hunter.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_API_URL = "https://remoteok.com/api"
_HEADERS = {"User-Agent": "job-hunter/1.0"}


class RemoteOKSource(JobSourceAdapter):
    global_feed = True

    @property
    def source_name(self) -> str:
        return "remoteok"

    def is_enabled(self, api_config: dict) -> bool:
        config = get_api_config().get("http", {}).get("job_boards", {}).get("remoteok", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch remote jobs from RemoteOK's public JSON feed."""
        source_config = get_api_config().get("http", {}).get("job_boards", {}).get("remoteok", {}) or {}
        if not source_config.get("enabled", True):
            return []

        timeout = int(source_config.get("timeout_seconds") or get_timeout("job_boards"))

        logger.info("[remoteok] Fetching job feed")
        try:
            resp = requests.get(_API_URL, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            logger.warning("[remoteok] request failed: %s", exc)
            return []

        if not isinstance(raw, list) or len(raw) < 2:
            return []

        # First element is legal/metadata dict — skip it
        items = raw[1:]

        jobs: list[JobPosting] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            job_title = str(item.get("position") or "")
            if not title_matches(job_title, params.job_titles, []):
                continue
            job_location = str(item.get("location") or "Remote")
            # Accept worldwide/remote postings; otherwise check against region location
            if params.location and job_location and job_location.lower() not in ("", "remote", "worldwide", "anywhere"):
                if not location_matches(job_location, params.location):
                    continue
            tags = item.get("tags") or []
            description = strip_html(str(item.get("description") or ""))
            snippet = description or ", ".join(str(t) for t in tags)
            jobs.append(
                JobPosting(
                    title=job_title,
                    company=str(item.get("company") or ""),
                    url=str(item.get("url") or ""),
                    posted_date_text=truncate_date_text(item.get("date")),
                    location=job_location,
                    snippet=snippet[:3000],
                    source="RemoteOK",
                    search_query=job_title,
                    region=params.region_key,
                    location_restrictions=[job_location]
                    if job_location and job_location.lower() not in ("remote", "")
                    else [],
                )
            )

        logger.info("[remoteok] %d jobs matched after filtering", len(jobs))
        return jobs
