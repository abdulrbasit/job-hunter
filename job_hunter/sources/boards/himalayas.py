"""Free Himalayas remote jobs API source."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.core.utils import strip_html, title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._http import fetch_title_pages
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import DEFAULT_SINGLE_PAGE_SOURCE_CAP, pages_for_max_results, source_page_cap

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://himalayas.app/jobs/api/search"
# Himalayas' API doesn't accept a page-size param; ~20 results/page is the observed default.
_PAGE_SIZE = 20


def _posted(value: Any) -> str:
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, tz=UTC).date().isoformat()
    if isinstance(value, str):
        return value[:10]
    return ""


def _location_text(job: dict[str, Any]) -> str:
    restrictions = job.get("locationRestrictions") or []
    names = []
    for item in restrictions:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item.get("name") or "").strip())
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    return ", ".join(names) if names else "Remote"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("name") or item.get("alpha2") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _float_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        try:
            result.append(float(item))
        except (TypeError, ValueError):
            continue
    return result


class HimalayasSource(JobSourceAdapter):
    # global_feed=True: orchestrator calls once with country="" (all remote jobs worldwide).
    # For single-region configs this has no call-count benefit, but for multi-region it
    # cuts calls from N_regions×N_titles to N_titles. No adapter-side country/location
    # rejection — Himalayas is a global remote board, so JobPolicy/quality_gate downstream
    # decide wrong-region using the location_restrictions metadata this adapter returns.
    global_feed = True

    @property
    def source_name(self) -> str:
        return "himalayas"

    def is_enabled(self, api_config: dict) -> bool:
        config = (api_config or {}).get("http", {}).get("job_boards", {}).get("himalayas", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch remote jobs from Himalayas' no-auth public API."""
        source_config = get_api_config().get("http", {}).get("job_boards", {}).get("himalayas", {}) or {}
        if not source_config.get("enabled", True):
            return []

        timeout = int(source_config.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = pages_for_max_results(
            params.max_results, _PAGE_SIZE, base_cap=source_page_cap(DEFAULT_SINGLE_PAGE_SOURCE_CAP)
        )
        iso = params.country.upper()
        jobs: list[JobPosting] = []

        for title, raw_jobs in fetch_title_pages(
            _SEARCH_URL,
            params.job_titles,
            lambda t, p: {"q": t, "country": iso, "sort": "recent", "page": p},
            "jobs",
            timeout=timeout,
            max_pages=max_pages,
            source_name="himalayas",
        ):
            before = len(jobs)
            for item in raw_jobs:
                job_title = str(item.get("title") or "")
                job_location = _location_text(item)
                if not title_is_allowed(job_title, params.job_titles, params.excluded_title_terms):
                    continue
                # Country/location filtering is deferred to JobPolicy/quality_gate downstream
                # (location_restrictions below carries the signal) — the API's own `country`
                # query param already does the server-side narrowing.
                description = strip_html(item.get("description") or item.get("excerpt") or "")
                jobs.append(
                    JobPosting(
                        title=job_title,
                        company=str(item.get("companyName") or ""),
                        url=str(item.get("applicationLink") or item.get("guid") or ""),
                        posted_date_text=_posted(item.get("pubDate")),
                        location=job_location,
                        snippet=description[:3000],
                        source="Himalayas",
                        search_query=f"{title} @ {params.region_key}",
                        region=params.region_key,
                        location_restrictions=_string_list(item.get("locationRestrictions")),
                        timezone_restrictions=_float_list(item.get("timezoneRestrictions")),
                        employment_type=str(item.get("employmentType") or ""),
                        seniority=_string_list(item.get("seniority")),
                    )
                )
            logger.info("[himalayas] +%d jobs for %r in %s", len(jobs) - before, title, params.region_key)

        return jobs
