from __future__ import annotations

import logging

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _SNIPPET_CHARS, _TIMEOUT

logger = logging.getLogger(__name__)


def fetch_smartrecruiters_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """
    Fetch jobs from SmartRecruiters public API (no auth required).
    Makes a second request per matched job to retrieve the full description.
    """
    params: dict = {"limit": 100}
    if location_filter:
        params["city"] = location_filter

    try:
        resp = requests.get(
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
            params=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json().get("content", [])
    except Exception as e:
        logger.warning(f"[smartrecruiters] {slug}: {e}")
        return []

    jobs = []
    for posting in postings:
        title = posting.get("name", "")
        loc = posting.get("location", {})
        city = loc.get("city", "")
        country = loc.get("country", "")
        location_str = f"{city}, {country}".strip(", ")

        if location_filter and city and not location_matches(city, location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        # Fetch full job description (N+1, only for filtered matches)
        posting_id = posting.get("id", "")
        snippet = location_str
        if posting_id:
            try:
                detail = requests.get(
                    f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}",
                    timeout=_TIMEOUT,
                )
                if detail.status_code == 200:
                    sections = detail.json().get("jobAd", {}).get("sections", [])
                    body = " ".join(f"{s.get('title', '')}: {strip_html(s.get('text', ''))}" for s in sections)
                    snippet = f"{location_str} - {body[:_SNIPPET_CHARS]}"
            except Exception as e:
                logger.debug(f"[smartrecruiters] detail fetch failed for {posting_id}: {e}")

        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": f"https://jobs.smartrecruiters.com/{slug}/{posting_id}",
                "posted": posting.get("releasedDate", ""),
                "location": location_str,
                "snippet": snippet,
                "employment_type": (posting.get("typeOfEmployment") or {}).get("label", ""),
                "source": "SmartRecruiters API",
            }
        )

    logger.info(f"[smartrecruiters] {slug}: {len(jobs)} matching jobs")
    return jobs
