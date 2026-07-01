"""ATS URL pattern detection and public endpoint fetching."""

from __future__ import annotations

import requests

from job_hunter.config.loader import get_timeout
from job_hunter.constants import CAREER_PAGE_SNIPPET_CHARS
from job_hunter.sources.ats_urls import ats_endpoint_patterns
from job_hunter.sources.search_providers import USER_AGENT

_ATS_URL_PATTERNS = ats_endpoint_patterns()

# Common career-page paths to probe when the base URL is not an ATS subdomain.
_CAREER_PATHS = [
    "/careers",
    "/jobs",
    "/job-openings",
    "/open-positions",
    "/work-with-us",
    "/join-us",
]


def detect_ats(url: str) -> tuple[str, str, str]:
    """Return (ats_name, slug, api_url_template) for the given URL, or ('', '', '') if unknown."""
    for pattern, ats_name, api_template in _ATS_URL_PATTERNS:
        m = pattern.search(url)
        if m:
            slug = m.group(1).rstrip("/")
            if ats_name == "workday":
                slug = slug.split(".", 1)[0]
            return ats_name, slug, api_template
    return "", "", ""


def detect_ats_from_url(url: str) -> tuple[str, str] | None:
    """Return (platform, slug) for a known ATS URL, or None if not recognized."""
    ats_name, slug, _ = detect_ats(url)
    if ats_name and slug:
        return (ats_name, slug)
    return None


def _normalise_ats_job(raw: dict, ats_name: str, slug: str, base_url: str) -> dict | None:
    """Convert a raw ATS API job object into a minimal job dict."""
    title = raw.get("title") or raw.get("text") or raw.get("name") or ""
    if not title:
        return None

    url = raw.get("absolute_url") or raw.get("hostedUrl") or raw.get("applyUrl") or raw.get("url") or ""

    # Greenhouse wraps location as an object
    location_raw = raw.get("location") or raw.get("locationName") or ""
    if isinstance(location_raw, dict):
        location = location_raw.get("name", "")
    else:
        location = str(location_raw)

    company = slug.replace("-", " ").replace("_", " ").title()

    return {
        "title": str(title).strip(),
        "company": company,
        "url": str(url).strip(),
        "location": location.strip(),
        "posted_date_text": str(raw.get("updated_at") or raw.get("createdAt") or "").strip(),
        "snippet": str(raw.get("content") or raw.get("description") or "")[:CAREER_PAGE_SNIPPET_CHARS].strip(),
        "source": f"career_page:ats_api:{ats_name}",
        "extraction_method": "ats_api",
        "detected_ats": ats_name,
    }


import logging  # noqa: E402

logger = logging.getLogger(__name__)


def _fetch_ats_endpoint_jobs(
    slug: str,
    ats_name: str,
    api_url_template: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None,
) -> list[dict]:
    if not api_url_template:
        return []

    api_url = api_url_template.format(slug=slug)
    timeout = get_timeout("ats_scraper")
    try:
        resp = requests.get(
            api_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[career_pages] ATS API fetch failed (%s, %s): %s", ats_name, slug, exc)
        return []

    # Normalise different ATS response shapes to a flat list of job dicts
    raw_jobs: list[dict] = []
    if isinstance(data, list):
        raw_jobs = data
    elif isinstance(data, dict):
        for key in ("jobs", "postings", "offers", "results", "content"):
            if isinstance(data.get(key), list):
                raw_jobs = data[key]
                break

    jobs = []
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        job = _normalise_ats_job(raw, ats_name, slug, api_url)
        if job and job.get("url"):
            jobs.append(job)

    logger.debug(
        "[career_pages] ATS API (%s, %s): %d raw -> %d normalised",
        ats_name,
        slug,
        len(raw_jobs),
        len(jobs),
    )
    return jobs
