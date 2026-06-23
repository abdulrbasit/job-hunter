from __future__ import annotations

import logging
import re

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _TIMEOUT, _build_snippet

logger = logging.getLogger(__name__)


def fetch_greenhouse_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Greenhouse public API (no auth required)."""
    try:
        resp = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            params={"content": "true"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        all_jobs = resp.json().get("jobs", [])
    except Exception as e:
        logger.warning(f"[greenhouse] {slug}: {e}")
        return []

    jobs = []
    for job in all_jobs:
        title = job.get("title", "")
        location = job.get("location", {}).get("name", "")
        url = job.get("absolute_url", "")
        content = strip_html(job.get("content", ""))
        posted = (job.get("updated_at") or "")[:10]

        if not url or not re.search(r"/jobs/\d+", url):
            logger.debug("[greenhouse] %s: skipping URL without numeric job ID: %s", slug, url)
            continue
        if not location_matches(location, location_filter):
            logger.debug(f"[greenhouse] skip wrong location: {title} ({location})")
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": posted,
                "location": location,
                "snippet": _build_snippet(location, content),
                "source": "Greenhouse API",
            }
        )

    logger.info(f"[greenhouse] {slug}: {len(jobs)} matching jobs")
    return jobs
