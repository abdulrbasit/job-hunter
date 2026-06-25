"""Free Himalayas remote jobs API source."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import requests

from job_hunter.config.loader import get_timeout, load_api_config
from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import DEFAULT_SINGLE_PAGE_SOURCE_CAP, source_page_cap, terminal_http_status

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://himalayas.app/jobs/api/search"


def _posted(value: Any) -> str:
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, tz=UTC).date().isoformat()
    if isinstance(value, str):
        return value[:10]
    return ""


def _country_matches(job: dict[str, Any], iso: str) -> bool:
    if not iso:
        return True
    restrictions = job.get("locationRestrictions") or []
    if not restrictions:
        return True
    return any(str(item.get("alpha2") or "").upper() == iso for item in restrictions if isinstance(item, dict))


def _location_text(job: dict[str, Any]) -> str:
    restrictions = job.get("locationRestrictions") or []
    names = [
        str(item.get("name") or "").strip() for item in restrictions if isinstance(item, dict) and item.get("name")
    ]
    return ", ".join(names) if names else "Remote"


class HimalayasSource(JobSourceAdapter):
    # global_feed=True: orchestrator calls once with country="" (all remote jobs worldwide).
    # For single-region configs this has no call-count benefit, but for multi-region it
    # cuts calls from N_regions×N_titles to N_titles. Country filter is skipped by design
    # — Himalayas is a global remote board so all-remote is the correct scope.
    global_feed = True

    @property
    def source_name(self) -> str:
        return "himalayas"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("himalayas", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch remote jobs from Himalayas' no-auth public API."""
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("himalayas", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap(DEFAULT_SINGLE_PAGE_SOURCE_CAP)
        iso = params.country.upper()
        location = params.location
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            for page in range(1, max_pages + 1):
                try:
                    resp = requests.get(
                        _SEARCH_URL,
                        params={"q": title, "country": iso, "sort": "recent", "page": page},
                        timeout=timeout,
                    )
                    resp.raise_for_status()
                    raw_jobs = resp.json().get("jobs", [])
                except Exception as exc:
                    logger.warning(
                        "[himalayas] failed for %r in %s page %s: %s",
                        title,
                        params.region_key,
                        page,
                        exc,
                    )
                    if terminal_http_status(exc):
                        return jobs
                    break

                if not raw_jobs:
                    break

                before = len(jobs)
                for item in raw_jobs:
                    job_title = str(item.get("title") or "")
                    job_location = _location_text(item)
                    if not title_matches(job_title, params.job_titles, []):
                        continue
                    if not _country_matches(item, iso):
                        continue
                    if location and job_location != "Remote" and not location_matches(job_location, location):
                        continue
                    description = strip_html(item.get("description") or item.get("excerpt") or "")
                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=str(item.get("companyName") or ""),
                            url=str(item.get("applicationLink") or item.get("guid") or ""),
                            posted=_posted(item.get("pubDate")),
                            location=job_location,
                            snippet=description[:3000],
                            source="Himalayas",
                            query=f"{title} @ {params.region_key}",
                            region=params.region_key,
                        )
                    )
                logger.info(
                    "[himalayas] +%d jobs for %r in %s",
                    len(jobs) - before,
                    title,
                    params.region_key,
                )

        return jobs
