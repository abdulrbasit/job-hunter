"""JobStreet — Southeast Asia job board (SG, MY, ID, PH, VN).

Tier 3: REST API with session headers first; falls back to Playwright.
Only fires for SEA regions (SG, MY, ID, PH, VN).
"""

from __future__ import annotations

import logging

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._dates import truncate_date_text
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import (
    sleep_between_pages,
    source_page_cap,
    source_page_delay,
    terminal_http_status,
)

logger = logging.getLogger(__name__)

_PAGE_SIZE = 30

# country ISO → (siteKey, domain)
_SEA_CONFIG: dict[str, tuple[str, str]] = {
    "SG": ("SG-Main", "jobstreet.com.sg"),
    "MY": ("MY-Main", "jobstreet.com.my"),
    "ID": ("ID-Main", "jobstreet.co.id"),
    "PH": ("PH-Main", "jobstreet.com.ph"),
    "VN": ("VN-Main", "jobstreet.com.vn"),
}


def _api_url(domain: str) -> str:
    return f"https://www.{domain}/api/chalice-search/v4/search"


def _job_url(domain: str, job_id: str) -> str:
    return f"https://www.{domain}/job/{job_id}"


def _headers(domain: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://www.{domain}/jobs/",
    }


class JobStreetSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "jobstreet"

    def is_enabled(self, api_config: dict) -> bool:
        config = get_api_config().get("http", {}).get("job_boards", {}).get("jobstreet", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from JobStreet (REST API, static only).

        Only runs for SEA regions (SG, MY, ID, PH, VN).
        """
        iso = params.country.upper()
        if iso not in _SEA_CONFIG:
            return []

        source_config = get_api_config().get("http", {}).get("job_boards", {}).get("jobstreet", {}) or {}
        if not source_config.get("enabled", True):
            return []

        timeout = int(source_config.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap()
        page_delay = source_page_delay()

        site_key, domain = _SEA_CONFIG[iso]
        api_url = _api_url(domain)
        req_headers = _headers(domain)
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            for page in range(1, max_pages + 1):
                try:
                    resp = requests.get(
                        api_url,
                        params={
                            "siteKey": site_key,
                            "keywords": title,
                            "page": page,
                            "pageSize": _PAGE_SIZE,
                            "sortMode": 1,
                        },
                        headers=req_headers,
                        timeout=timeout,
                    )
                    if resp.status_code == 429:
                        logger.warning("[jobstreet] rate limited; stopping source for this run")
                        return jobs
                    if resp.status_code in (403, 503):
                        logger.debug(
                            "[jobstreet] %d for %r in %s; skipping page",
                            resp.status_code,
                            title,
                            params.region_key,
                        )
                        break
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    if terminal_http_status(exc):
                        logger.warning("[jobstreet] stopping after terminal HTTP error: %s", exc)
                        return jobs
                    logger.warning(
                        "[jobstreet] failed for %r in %s page %d: %s",
                        title,
                        params.region_key,
                        page,
                        exc,
                    )
                    break

                items = (data.get("data") or {}).get("jobs") or data.get("jobs") or []
                if not items:
                    break

                before = len(jobs)
                for item in items:
                    job_title = str(item.get("title") or "")
                    if not title_matches(job_title, params.job_titles, []):
                        continue

                    advertiser = item.get("advertiser") or {}
                    company = str(advertiser.get("description") or advertiser.get("name") or "")
                    job_id = str(item.get("id") or "")
                    job_url = _job_url(domain, job_id) if job_id else ""

                    salary_obj = item.get("salary") or {}
                    salary_min = salary_obj.get("min") or salary_obj.get("minimum")
                    salary_max = salary_obj.get("max") or salary_obj.get("maximum")
                    posted = truncate_date_text(item.get("listingDate") or item.get("postedDate"))
                    teaser = strip_html(str(item.get("teaser") or item.get("description") or ""))
                    snippet = teaser
                    if salary_min and salary_max:
                        snippet = f"Salary: {salary_min}–{salary_max}. " + snippet

                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=company,
                            url=job_url,
                            posted_date_text=posted,
                            location=params.location or iso,
                            snippet=snippet[:3000],
                            source="JobStreet",
                            search_query=f"{title} @ {params.region_key}",
                            region=params.region_key,
                        )
                    )
                logger.info(
                    "[jobstreet] +%d jobs for %r in %s page %d/%d",
                    len(jobs) - before,
                    title,
                    params.region_key,
                    page,
                    max_pages,
                )

                if len(items) < _PAGE_SIZE:
                    break
                if page == max_pages:
                    logger.warning(
                        "[jobstreet] reached page cap=%d for %r in %s; stopping",
                        max_pages,
                        title,
                        params.region_key,
                    )
                    break
                sleep_between_pages(page_delay, page, max_pages)

        logger.info("[jobstreet] Complete: %d total jobs", len(jobs))
        return jobs
