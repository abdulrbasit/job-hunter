from __future__ import annotations

import logging

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _TIMEOUT, _build_snippet

logger = logging.getLogger(__name__)


def fetch_breezy_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Breezy's public JSON feed."""
    try:
        resp = requests.get(f"https://{slug}.breezy.hr/json", params={"verbose": "true"}, timeout=_TIMEOUT)
        resp.raise_for_status()
        postings = resp.json()
    except Exception as e:
        logger.warning(f"[breezy] {slug}: {e}")
        return []

    if isinstance(postings, dict):
        postings = postings.get("positions") or postings.get("jobs") or []

    jobs = []
    for posting in postings:
        title = posting.get("name") or posting.get("title") or ""
        location = posting.get("location") or ""
        if isinstance(location, dict):
            location = ", ".join(str(v) for v in location.values() if v)
        if location_filter and location and not location_matches(str(location), location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        body = strip_html(posting.get("description") or "")
        slug_or_id = posting.get("friendly_id") or posting.get("id") or ""
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": posting.get("url") or f"https://{slug}.breezy.hr/p/{slug_or_id}",
                "posted": (posting.get("creation_date") or posting.get("published_at") or "")[:10],
                "location": str(location),
                "snippet": _build_snippet(location, body),
                "source": "Breezy JSON",
            }
        )

    logger.info(f"[breezy] {slug}: {len(jobs)} matching jobs")
    return jobs
