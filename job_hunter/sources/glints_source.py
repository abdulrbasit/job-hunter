"""Glints — Southeast Asia job board (SG, ID, MY, VN, PH).

Unofficial REST-like JSON API. No auth required.
The Glints market also includes TH and TW, but this adapter only fires for
currently mapped SEA regions (SG, ID, MY, VN, PH).
"""

from __future__ import annotations

import logging

import requests

from job_hunter.core.config import get_timeout, load_api_config
from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import (
    sleep_between_pages,
    source_page_cap,
    source_page_delay,
)

logger = logging.getLogger(__name__)

_API_URL = "https://glints.com/api/jobs"
_JOB_BASE = "https://glints.com/opportunities/jobs"
_PAGE_SIZE = 30

_SEA_CODES: frozenset[str] = frozenset({"SG", "ID", "MY", "VN", "PH"})

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://glints.com/",
}


def _extract_items(data: object) -> list:
    """Return Glints job items across API response shape variants."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []

    nested = data.get("data") or {}
    if isinstance(nested, list):
        return nested
    if isinstance(nested, dict):
        items = nested.get("jobs") or nested.get("data") or []
        if isinstance(items, dict):
            items = items.get("data") or items.get("jobs") or []
        return items if isinstance(items, list) else []

    items = data.get("jobs") or []
    return items if isinstance(items, list) else []


class GlintsSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "glints"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("glints", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from Glints for SEA regions.

        Only runs for regions whose country code is in SG, ID, MY, VN, PH.
        """
        iso = params.country.upper()
        if iso not in _SEA_CODES:
            return []

        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("glints", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap()
        page_delay = source_page_delay()
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            for page in range(1, max_pages + 1):
                try:
                    resp = requests.get(
                        _API_URL,
                        params={
                            "query": title,
                            "countryCode": iso,
                            "page": page,
                            "pageSize": _PAGE_SIZE,
                        },
                        headers=_HEADERS,
                        timeout=timeout,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.warning(
                        "[glints] failed for %r in %s page %d: %s",
                        title,
                        params.region_key,
                        page,
                        exc,
                    )
                    break

                items = _extract_items(data)
                if not items:
                    break

                before = len(jobs)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    job_title = str(item.get("title") or item.get("name") or "")
                    if not title_matches(job_title, params.job_titles, []):
                        continue

                    company_obj = item.get("company") or item.get("organisation") or {}
                    company = str(company_obj.get("name") if isinstance(company_obj, dict) else "")
                    job_id = str(item.get("id") or item.get("uuid") or "")
                    job_url = f"{_JOB_BASE}/{job_id}" if job_id else ""

                    city_obj = item.get("city") or {}
                    country_obj = item.get("country") or {}
                    city = str(city_obj.get("name") if isinstance(city_obj, dict) else city_obj or "")
                    country_name = str(country_obj.get("name") if isinstance(country_obj, dict) else country_obj or iso)
                    job_location = ", ".join(filter(None, [city, country_name]))

                    created_at = str(item.get("createdAt") or item.get("created_at") or "")[:10]
                    description = strip_html(str(item.get("description") or ""))

                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=company,
                            url=job_url,
                            posted=created_at,
                            location=job_location,
                            snippet=description[:3000],
                            source="Glints",
                            query=f"{title} @ {params.region_key}",
                            region=params.region_key,
                        )
                    )
                logger.info(
                    "[glints] +%d jobs for %r in %s page %d/%d",
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
                        "[glints] reached page cap=%d for %r in %s; stopping",
                        max_pages,
                        title,
                        params.region_key,
                    )
                    break
                sleep_between_pages(page_delay, page, max_pages)

        logger.info("[glints] Complete: %d total jobs", len(jobs))
        return jobs
