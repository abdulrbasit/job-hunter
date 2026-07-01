from __future__ import annotations

import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_hunter.core.utils import location_matches, title_matches
from job_hunter.sources.ats._base import _TIMEOUT

logger = logging.getLogger(__name__)


def fetch_teamtailor_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Extract public job links from a Teamtailor careers page."""
    base_url = f"https://{slug}.teamtailor.com/jobs"
    try:
        resp = requests.get(base_url, timeout=_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[teamtailor] {slug}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen: set[str] = set()
    jobs = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if "/jobs/" not in href:
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        title = " ".join((anchor.get_text(" ") or "").split())
        if not title or not title_matches(title, title_filters, excluded_title_terms):
            continue
        parent = anchor.parent
        location_tag = (
            parent.find(["span", "p", "div"], class_=lambda c: c and "location" in c.lower()) if parent else None
        )
        location = " ".join((location_tag.get_text(" ") or "").split()) if location_tag else ""
        if location_filter and location and not location_matches(location, location_filter):
            continue
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted_date_text": "",
                "location": location,
                "snippet": "",
                "source": "Teamtailor",
            }
        )

    logger.info(f"[teamtailor] {slug}: {len(jobs)} matching jobs")
    return jobs
