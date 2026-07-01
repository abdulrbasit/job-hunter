"""HeadHunter (hh.ru) job board — Russia and CIS countries.

Free public REST API, no authentication required.
API docs: https://github.com/hhru/api/blob/master/docs/vacancies.md

Covers: RU (Russia), KZ (Kazakhstan), UA (Ukraine), BY (Belarus),
        AZ (Azerbaijan), AM (Armenia).
"""

from __future__ import annotations

import logging

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.core.utils import title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._dates import truncate_date_text
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import source_page_cap, terminal_http_status

logger = logging.getLogger(__name__)

_API_URL = "https://api.hh.ru/vacancies"
_PAGE_SIZE = 100

# ISO 3166-1 alpha-2 → hh.ru area ID
_ISO_TO_HH_AREA: dict[str, int] = {
    "RU": 113,  # Russia
    "KZ": 40,  # Kazakhstan
    "UA": 5,  # Ukraine
    "BY": 16,  # Belarus
    "AZ": 97,  # Azerbaijan
    "AM": 149,  # Armenia
}

_HEADERS = {
    "User-Agent": "job-hunter/1.0 (job search automation; contact via github.com/abdulrbasit/job-hunter)",
    "HH-User-Agent": "job-hunter/1.0",
}


class HHSource(JobSourceAdapter):
    tier = "free"

    @property
    def source_name(self) -> str:
        return "hh"

    def is_enabled(self, api_config: dict) -> bool:
        config = get_api_config().get("http", {}).get("job_boards", {}).get("hh", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from hh.ru for Russia/CIS regions."""
        config = get_api_config().get("http", {}).get("job_boards", {}).get("hh", {}) or {}
        if not config.get("enabled", True):
            return []

        iso = params.country.upper()
        area_id = _ISO_TO_HH_AREA.get(iso)
        if area_id is None:
            return []

        timeout = int(config.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap()
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            logger.info("[hh] [%s] Searching area=%d for %r", params.region_key, area_id, title)
            for page in range(0, max_pages):
                req_params: dict = {
                    "text": title,
                    "area": area_id,
                    "per_page": _PAGE_SIZE,
                    "page": page,
                    "search_field": "name",
                }
                if params.location:
                    req_params["text"] = f"{title} {params.location}"

                try:
                    resp = requests.get(_API_URL, params=req_params, headers=_HEADERS, timeout=timeout)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    if terminal_http_status(exc):
                        logger.warning("[hh] terminal HTTP failure; stopping: %s", exc)
                        return jobs
                    logger.warning("[hh] request failed for %r in %s page %d: %s", title, params.region_key, page, exc)
                    break

                items = data.get("items") or []
                if not items:
                    break

                before = len(jobs)
                for item in items:
                    job_title = str(item.get("name") or "")
                    if not title_is_allowed(job_title, params.job_titles, params.excluded_title_terms):
                        continue
                    snippet_data = item.get("snippet") or {}
                    snippet = str(snippet_data.get("requirement") or snippet_data.get("responsibility") or "")
                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=str((item.get("employer") or {}).get("name") or ""),
                            url=str(item.get("alternate_url") or ""),
                            posted_date_text=truncate_date_text(item.get("published_at")),
                            location=str((item.get("area") or {}).get("name") or params.location),
                            snippet=snippet[:3000],
                            source="hh.ru",
                            search_query=f"{title} @ {params.region_key}",
                            region=params.region_key,
                        )
                    )

                logger.info("[hh] +%d jobs for %r in %s (p%d)", len(jobs) - before, title, params.region_key, page)

                total_pages = int(data.get("pages") or 1)
                if page + 1 >= total_pages:
                    break

        logger.info("[hh] Complete: %d total jobs found", len(jobs))
        return jobs
