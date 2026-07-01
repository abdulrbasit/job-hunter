"""MyCareersFuture.sg — Singapore government job portal (official REST API).

Free, no API key required. Only fires for regions with country == "SG".
"""

from __future__ import annotations

import logging

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import (
    sleep_between_pages,
    source_page_cap,
    source_page_delay,
    terminal_http_status,
)

logger = logging.getLogger(__name__)

_API_URL = "https://api.mycareersfuture.gov.sg/v2/jobs"
_JOB_BASE_URL = "https://www.mycareersfuture.gov.sg/job"
_PAGE_SIZE = 100


class MyCareersFutureSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "mycareersfuture"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = get_api_config().get("http", {}).get("job_boards", {}).get("mycareersfuture", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from MyCareersFuture.sg official REST API.

        Only runs for Singapore regions (country == SG).
        """
        if params.country.upper() != "SG":
            return []

        source_cfg = get_api_config().get("http", {}).get("job_boards", {}).get("mycareersfuture", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap()
        page_delay = source_page_delay()
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            for page in range(max_pages):
                try:
                    resp = requests.get(
                        _API_URL,
                        params={"search": title, "limit": _PAGE_SIZE, "page": page},
                        timeout=timeout,
                        headers={"Accept": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    if terminal_http_status(exc):
                        logger.warning("[mycareersfuture] stopping after terminal HTTP error: %s", exc)
                        return jobs
                    logger.warning(
                        "[mycareersfuture] failed for %r in %s page %d: %s",
                        title,
                        params.region_key,
                        page,
                        exc,
                    )
                    break

                results = data.get("results") or []
                if not results:
                    break

                before = len(jobs)
                for item in results:
                    job_title = str(item.get("title") or "")
                    if not title_matches(job_title, params.job_titles, []):
                        continue

                    uid = str(item.get("uuid") or "")
                    company = str(
                        (item.get("postedCompany") or {}).get("name")
                        or (item.get("hiringCompany") or {}).get("name")
                        or ""
                    )
                    description = strip_html(str(item.get("description") or ""))
                    metadata = item.get("metadata") or {}
                    dates = metadata.get("dates") or {}
                    posted = str(dates.get("posting") or dates.get("created") or "")[:10]
                    salary_obj = item.get("salary") or {}
                    salary_min = salary_obj.get("minimum")
                    salary_max = salary_obj.get("maximum")
                    location_parts = []
                    addr = item.get("address") or {}
                    if addr.get("street"):
                        location_parts.append(str(addr["street"]))
                    location_parts.append("Singapore")
                    location = ", ".join(location_parts)

                    snippet = description[:3000]
                    if salary_min and salary_max:
                        snippet = f"Salary: SGD {salary_min}–{salary_max}/mo. " + snippet

                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=company,
                            url=f"{_JOB_BASE_URL}/{uid}" if uid else "",
                            posted_date_text=posted,
                            location=location,
                            snippet=snippet,
                            source="MyCareersFuture",
                            search_query=f"{title} @ {params.region_key}",
                            region=params.region_key,
                        )
                    )
                logger.info(
                    "[mycareersfuture] +%d jobs for %r in %s page %d/%d",
                    len(jobs) - before,
                    title,
                    params.region_key,
                    page + 1,
                    max_pages,
                )

                if len(results) < _PAGE_SIZE:
                    break
                if page + 1 == max_pages:
                    logger.warning(
                        "[mycareersfuture] reached page cap=%d for %r in %s; stopping",
                        max_pages,
                        title,
                        params.region_key,
                    )
                    break
                sleep_between_pages(page_delay, page + 1, max_pages)

        logger.info("[mycareersfuture] Complete: %d total jobs", len(jobs))
        return jobs
