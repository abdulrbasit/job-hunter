from __future__ import annotations

import logging

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _TIMEOUT, _build_snippet

logger = logging.getLogger(__name__)


def fetch_recruitee_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Recruitee's public careers API."""
    try:
        resp = requests.get(f"https://{slug}.recruitee.com/api/offers/", timeout=_TIMEOUT)
        resp.raise_for_status()
        offers = resp.json().get("offers", [])
    except Exception as e:
        logger.warning(f"[recruitee] {slug}: {e}")
        return []

    jobs = []
    for offer in offers:
        title = offer.get("title", "")
        location = offer.get("location", "") or offer.get("city", "")
        if isinstance(location, dict):
            location = ", ".join(str(v) for v in location.values() if v)
        if location_filter and location and not location_matches(str(location), location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        body = strip_html(offer.get("description") or offer.get("description_html") or "")
        url = offer.get("careers_url") or offer.get("url") or f"https://{slug}.recruitee.com/o/{offer.get('slug', '')}"
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": (offer.get("published_at") or "")[:10],
                "location": str(location),
                "snippet": _build_snippet(location, body),
                "source": "Recruitee API",
            }
        )

    logger.info(f"[recruitee] {slug}: {len(jobs)} matching jobs")
    return jobs
