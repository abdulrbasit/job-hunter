from __future__ import annotations

import logging

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _SNIPPET_CHARS, _TIMEOUT

logger = logging.getLogger(__name__)

_CAREERS_URL = "https://{slug}.bamboohr.com/careers/list"
_JOB_URL = "https://{slug}.bamboohr.com/careers/{job_id}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_bamboohr_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from BambooHR public careers API (no auth required)."""
    headers = {**_HEADERS, "Referer": f"https://{slug}.bamboohr.com/careers", "Origin": f"https://{slug}.bamboohr.com"}
    try:
        resp = requests.get(
            _CAREERS_URL.format(slug=slug),
            headers=headers,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("[bamboohr] %s: %s", slug, e)
        return []

    postings = data.get("result") or []
    if not isinstance(postings, list):
        return []

    jobs = []
    for posting in postings:
        title = posting.get("jobOpeningName", "")
        city = posting.get("locationCity", "")
        country = posting.get("locationCountry", "")
        location = f"{city}, {country}".strip(", ") if city or country else ""
        job_id = str(posting.get("id", ""))
        url = _JOB_URL.format(slug=slug, job_id=job_id) if job_id else ""
        department = posting.get("departmentLabel", "")
        description = strip_html(posting.get("description", "") or "")
        posted = str(posting.get("datePosted", ""))[:10]

        if location_filter and location:
            if not location_matches(city, location_filter) and not location_matches(location, location_filter):
                logger.debug("[bamboohr] skip wrong location: %s (%s)", title, location)
                continue

        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        snippet_parts = [s for s in [location, department, description[:_SNIPPET_CHARS]] if s]
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted_date_text": posted,
                "location": location,
                "snippet": " — ".join(snippet_parts[:2]) + (f"\n{description[:_SNIPPET_CHARS]}" if description else ""),
                "source": "BambooHR",
            }
        )

    logger.info("[bamboohr] %s: %d matching jobs", slug, len(jobs))
    return jobs
