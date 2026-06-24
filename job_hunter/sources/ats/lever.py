from __future__ import annotations

import logging
from datetime import datetime

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _SNIPPET_CHARS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASES = ("https://api.lever.co", "https://api.eu.lever.co")


def _get_postings(slug: str) -> list:
    for base in _BASES:
        try:
            resp = requests.get(f"{base}/v0/postings/{slug}", params={"mode": "json"}, timeout=_TIMEOUT)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("postings", [])
        except Exception as e:
            logger.warning("[lever] %s via %s: %s", slug, base, e)
    return []


def fetch_lever_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Lever public API (no auth required). Tries EU endpoint on 404."""
    postings = _get_postings(slug)

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
                logger.debug("[lever] skip wrong location: %s (%s)", title, all_locations)
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

    logger.info("[lever] %s: %d matching jobs", slug, len(jobs))
    return jobs
