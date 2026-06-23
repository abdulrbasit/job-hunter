from __future__ import annotations

import logging
from datetime import datetime

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _SNIPPET_CHARS, _TIMEOUT

logger = logging.getLogger(__name__)


def fetch_lever_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Lever public API (no auth required)."""
    try:
        resp = requests.get(
            f"https://api.lever.co/v0/postings/{slug}",
            params={"mode": "json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json()
    except Exception as e:
        logger.warning(f"[lever] {slug}: {e}")
        return []

    if isinstance(postings, dict):
        postings = postings.get("postings", [])

    jobs = []
    for posting in postings:
        title = posting.get("text", "")
        categories = posting.get("categories", {})
        primary = categories.get("location", "")
        all_locations = list(categories.get("allLocations") or ([primary] if primary else []))
        if primary and primary not in all_locations:
            all_locations.insert(0, primary)

        url = posting.get("hostedUrl", "")
        plain = posting.get("descriptionPlain") or strip_html(posting.get("description", ""))
        created_ms = posting.get("createdAt")
        posted = datetime.fromtimestamp(created_ms / 1000).strftime("%Y-%m-%d") if created_ms else ""

        if location_filter and all_locations:
            if not any(location_matches(loc, location_filter) for loc in all_locations):
                logger.debug(f"[lever] skip wrong location: {title} ({all_locations})")
                continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        display_location = primary or (all_locations[0] if all_locations else "")
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": posted,
                "location": display_location,
                "snippet": (
                    f"{display_location} - {plain[:_SNIPPET_CHARS]}" if display_location else plain[:_SNIPPET_CHARS]
                ),
                "source": "Lever API",
            }
        )

    logger.info(f"[lever] {slug}: {len(jobs)} matching jobs")
    return jobs
