"""Adzuna job board source — free official API with global coverage.

Supports: AU, AT, BE, BR, CA, DE, ES, FR, GB, IT, MX, NL, NZ, PL, SG, US, ZA, CH, IN.
Register for a free API key at https://developer.adzuna.com/

The Adzuna country is derived automatically from each region's ISO country code
(the `country` field in config/job_hunter.yml regions). No mapping config needed.

Required env vars (both optional — source skips silently if absent):
  ADZUNA_APP_ID   — application ID from developer.adzuna.com
  ADZUNA_API_KEY  — API key from developer.adzuna.com
"""

from __future__ import annotations

import logging
from datetime import datetime

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.config.secrets import ADZUNA_API_KEY, ADZUNA_APP_ID
from job_hunter.core.utils import title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import (
    DEFAULT_SINGLE_PAGE_SOURCE_CAP,
    pages_for_max_results,
    source_page_cap,
    terminal_http_status,
)

logger = logging.getLogger(__name__)

_TIMEOUT = get_timeout("job_boards")
_BASE_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

# ISO 3166-1 alpha-2 → Adzuna country code (only supported countries listed)
_ISO_TO_ADZUNA: dict[str, str] = {
    "AU": "au",
    "AT": "at",
    "BE": "be",
    "BR": "br",
    "CA": "ca",
    "DE": "de",
    "ES": "es",
    "FR": "fr",
    "GB": "gb",
    "IE": "gb",  # Adzuna gb covers Ireland
    "IN": "in",
    "IT": "it",
    "MX": "mx",
    "NL": "nl",
    "NZ": "nz",
    "PL": "pl",
    "SG": "sg",
    "CH": "ch",
    "US": "us",
    "ZA": "za",
}


def _parse_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


class AdzunaSource(JobSourceAdapter):
    tier = "api"

    def __init__(self) -> None:
        self._app_id: str = ADZUNA_APP_ID
        self._api_key: str = ADZUNA_API_KEY

    @property
    def source_name(self) -> str:
        return "adzuna"

    def is_enabled(self, api_config: dict) -> bool:
        config = (api_config or {}).get("http", {}).get("job_boards", {}).get("adzuna", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """
        Fetch jobs from Adzuna for a region whose ISO country code is supported.
        Returns [] silently if credentials are missing or adzuna is disabled.
        """
        if not self._app_id or not self._api_key:
            logger.warning("[adzuna] ADZUNA_APP_ID or ADZUNA_API_KEY not set — skipping")
            return []

        adzuna_config = get_api_config().get("http", {}).get("job_boards", {}).get("adzuna", {}) or {}
        if not adzuna_config.get("enabled", True):
            return []

        iso = params.country.upper()
        country = _ISO_TO_ADZUNA.get(iso, "")
        if not country:
            return []

        results_per_page = int(adzuna_config.get("results_per_page", 50))
        max_pages = pages_for_max_results(
            params.max_results, results_per_page, base_cap=source_page_cap(DEFAULT_SINGLE_PAGE_SOURCE_CAP)
        )
        location = params.location
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            logger.info("[adzuna] [%s] Searching country=%r for %r", params.region_key, country, title)
            req_params: dict = {
                "app_id": self._app_id,
                "app_key": self._api_key,
                "what": title,
                "results_per_page": results_per_page,
                "content-type": "application/json",
            }
            if location:
                req_params["where"] = location

            for page in range(1, max_pages + 1):
                url = _BASE_URL.format(country=country, page=page)
                try:
                    resp = requests.get(url, params=req_params, timeout=_TIMEOUT)
                    resp.raise_for_status()
                    data = resp.json().get("results", [])
                except Exception as exc:
                    if terminal_http_status(exc):
                        logger.warning("[adzuna] terminal HTTP failure; disabling for this run: %s", exc)
                        return jobs
                    logger.warning(
                        "[adzuna] request failed for %r in %r page %s: %s",
                        title,
                        params.region_key,
                        page,
                        exc,
                    )
                    break

                if not data:
                    break

                before = len(jobs)
                for item in data:
                    job_title = item.get("title", "")
                    if not title_is_allowed(job_title, params.job_titles, params.excluded_title_terms):
                        continue

                    location_str = item.get("location", {}).get("display_name", "")
                    description = (item.get("description") or "")[:1000]
                    snippet = f"{location_str} — {description}" if location_str else description

                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=item.get("company", {}).get("display_name", ""),
                            url=item.get("redirect_url", ""),
                            posted_date_text=_parse_date(item.get("created")),
                            location=location_str,
                            snippet=snippet,
                            source="Adzuna",
                            search_query=f"{title} @ {params.region_key}",
                            region=params.region_key,
                        )
                    )

                logger.info(
                    "[adzuna] +%d jobs for %r in %r page %s",
                    len(jobs) - before,
                    title,
                    params.region_key,
                    page,
                )
                if len(data) < results_per_page:
                    break

        logger.info("[adzuna] Complete: %d total jobs found", len(jobs))
        return jobs
