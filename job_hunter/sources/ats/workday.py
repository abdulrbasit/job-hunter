from __future__ import annotations

import logging
from urllib.parse import urljoin

import requests

from job_hunter.core.utils import location_matches, title_matches
from job_hunter.sources.ats._base import _TIMEOUT

logger = logging.getLogger(__name__)


def fetch_workday_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch Workday jobs from the public CXS listing endpoint where available."""
    host_site = slug.strip("/")
    if "/" not in host_site:
        return []
    host, site = host_site.split("/", 1)
    tenant = host.split(".")[0]
    base = f"https://{host}"
    try:
        resp = requests.post(
            f"{base}/wday/cxs/{tenant}/{site}/jobs",
            json={"appliedFacets": {}, "limit": 50, "offset": 0, "searchText": ""},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json().get("jobPostings", [])
    except Exception as e:
        logger.warning(f"[workday] {host_site}: {e}")
        return []

    jobs = []
    for posting in postings:
        title = posting.get("title", "")
        location = posting.get("locationsText") or posting.get("location") or ""
        if location_filter and location and not location_matches(location, location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        external_path = posting.get("externalPath") or ""
        url = urljoin(f"{base}/{site}/", external_path.lstrip("/")) if external_path else f"{base}/{site}"
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": posting.get("postedOn", ""),
                "location": location,
                "snippet": location,
                "source": "Workday CXS",
            }
        )

    logger.info(f"[workday] {host_site}: {len(jobs)} matching jobs")
    return jobs
