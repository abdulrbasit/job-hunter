from __future__ import annotations

import logging

import requests

from job_hunter.core.utils import location_matches, title_matches
from job_hunter.sources.ats._base import _TIMEOUT

logger = logging.getLogger(__name__)


def fetch_workable_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Workable public API (no auth required)."""
    try:
        resp = requests.post(
            f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
            json={"query": "", "location": [location_filter] if location_filter else []},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json().get("results", [])
    except Exception as e:
        logger.warning(f"[workable] {slug}: {e}")
        return []

    jobs = []
    for posting in postings:
        title = posting.get("title", "")
        location_str = posting.get("location", {}).get("location", "")

        if location_filter and location_str and not location_matches(location_str, location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        shortcode = posting.get("shortcode", "")
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": f"https://apply.workable.com/{slug}/j/{shortcode}",
                "posted": posting.get("published_on", ""),
                "location": location_str,
                "snippet": f"{location_str} - {posting.get('department', '')}",
                "employment_type": posting.get("employment_type", ""),
                "source": "Workable API",
            }
        )

    logger.info(f"[workable] {slug}: {len(jobs)} matching jobs")
    return jobs
