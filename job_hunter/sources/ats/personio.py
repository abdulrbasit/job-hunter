from __future__ import annotations

import logging
from xml.etree import ElementTree

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _TIMEOUT, _build_snippet

logger = logging.getLogger(__name__)


def fetch_personio_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Personio's public XML feed."""
    try:
        resp = requests.get(f"https://{slug}.jobs.personio.de/xml", timeout=_TIMEOUT)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
    except Exception as e:
        logger.warning(f"[personio] {slug}: {e}")
        return []

    jobs = []
    for position in root.findall(".//position"):
        title = (position.findtext("name") or "").strip()
        location = (position.findtext("office") or "").strip()
        if location_filter and location and not location_matches(location, location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        job_id = (position.findtext("id") or "").strip()
        descriptions = []
        for node in position.findall(".//jobDescription"):
            label = (node.findtext("name") or "").strip()
            value = strip_html(node.findtext("value") or "")
            if value:
                descriptions.append(f"{label}: {value}" if label else value)
        body = " ".join(descriptions)
        employment_type = (position.findtext("schedule") or position.findtext("employment_type") or "").strip()
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": f"https://{slug}.jobs.personio.de/job/{job_id}"
                if job_id
                else f"https://{slug}.jobs.personio.de",
                "posted_date_text": "",
                "location": location,
                "snippet": _build_snippet(location, body),
                "employment_type": employment_type,
                "source": "Personio XML",
            }
        )

    logger.info(f"[personio] {slug}: {len(jobs)} matching jobs")
    return jobs
