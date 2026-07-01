"""Free Bundesagentur fuer Arbeit Jobsuche source for German regions."""

from __future__ import annotations

import logging
from typing import Any

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.core.utils import location_matches, title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._dates import truncate_date_text
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import terminal_http_status

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/app/jobs"
_DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{0}"

# Arbeitsagentur requires German city names; English names return 0 results.
_DE_CITY_NAMES: dict[str, str] = {
    "Munich": "München",
    "Cologne": "Köln",
    "Nuremberg": "Nürnberg",
    "Dusseldorf": "Düsseldorf",
    "Düsseldorf": "Düsseldorf",
}


def _location(item: dict[str, Any]) -> str:
    place = item.get("arbeitsort") or {}
    if isinstance(place, dict):
        return ", ".join(str(place.get(key) or "").strip() for key in ("ort", "land") if place.get(key))
    return ""


class ArbeitsagenturSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "arbeitsagentur"

    def is_enabled(self, api_config: dict) -> bool:
        config = get_api_config().get("http", {}).get("job_boards", {}).get("arbeitsagentur", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch German public employment-agency jobs for DE regions."""
        if params.country.upper() != "DE":
            return []

        source_config = get_api_config().get("http", {}).get("job_boards", {}).get("arbeitsagentur", {}) or {}
        if not source_config.get("enabled", True):
            return []

        timeout = int(source_config.get("timeout_seconds") or get_timeout("job_boards"))
        size = int(source_config.get("results_per_query", 25))
        location = params.location
        wo_location = _DE_CITY_NAMES.get(location, location)
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            try:
                resp = requests.get(
                    _SEARCH_URL,
                    params={"was": title, "wo": wo_location, "page": 1, "size": size},
                    headers={"X-API-Key": "jobboerse-jobsuche"},
                    timeout=timeout,
                )
                resp.raise_for_status()
                postings = resp.json().get("stellenangebote", [])
            except Exception as exc:
                logger.warning("[arbeitsagentur] failed for %r in %s: %s", title, params.region_key, exc)
                if terminal_http_status(exc):
                    return jobs
                continue

            before = len(jobs)
            for item in postings:
                job_title = str(item.get("titel") or "")
                job_location = _location(item)
                if not title_is_allowed(job_title, params.job_titles, params.excluded_title_terms):
                    continue
                if location and job_location and not location_matches(job_location, location):
                    continue
                ref = str(item.get("refnr") or item.get("hashId") or "")
                jobs.append(
                    JobPosting(
                        title=job_title,
                        company=str(item.get("arbeitgeber") or ""),
                        url=_DETAIL_URL.format(ref) if ref else "",
                        posted_date_text=truncate_date_text(item.get("aktuelleVeroeffentlichungsdatum")),
                        location=job_location,
                        snippet=str(item.get("stellenbeschreibung") or item.get("beruf") or "")[:3000],
                        source="Arbeitsagentur",
                        search_query=f"{title} @ {params.region_key}",
                        region=params.region_key,
                    )
                )
            logger.info(
                "[arbeitsagentur] +%d jobs for %r in %s",
                len(jobs) - before,
                title,
                params.region_key,
            )

        return jobs
