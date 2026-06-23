from __future__ import annotations

import logging

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _TIMEOUT, _build_snippet

logger = logging.getLogger(__name__)


def fetch_ashby_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Ashby public job-board API (no auth required)."""
    try:
        resp = requests.post(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            json={},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json().get("jobPostings", [])
    except Exception as e:
        logger.warning(f"[ashby] {slug}: {e}")
        return []

    jobs = []
    for posting in postings:
        title = posting.get("title", "")
        location = posting.get("locationName", "")

        if not location_matches(location, location_filter):
            logger.debug(f"[ashby] skip wrong location: {title} ({location})")
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        description = strip_html(posting.get("descriptionHtml", ""))
        url = posting.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{posting.get('id', '')}"
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": (posting.get("publishedAt") or "")[:10],
                "location": location,
                "snippet": _build_snippet(location, description),
                "source": "Ashby API",
            }
        )

    logger.info(f"[ashby] {slug}: {len(jobs)} matching jobs")
    return jobs
