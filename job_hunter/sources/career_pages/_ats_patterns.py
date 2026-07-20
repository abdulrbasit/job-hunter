"""ATS URL pattern detection and public endpoint fetching."""

from __future__ import annotations

import requests

from job_hunter.config.loader import get_timeout
from job_hunter.constants import CAREER_PAGE_SNIPPET_CHARS
from job_hunter.sources.ats_urls import ats_endpoint_patterns
from job_hunter.sources.search import USER_AGENT

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
    if not location:
        # Teamtailor: location lives in the embedded schema.org JobPosting instead.
        job_locations = ((raw.get("_jobposting") or {}).get("jobLocation")) or []
        if job_locations and isinstance(job_locations, list):
            address = (job_locations[0] or {}).get("address") or {}
            location = ", ".join(filter(None, [address.get("addressLocality", ""), address.get("addressCountry", "")]))

    company = slug.replace("-", " ").replace("_", " ").title()

    description = raw.get("content") or raw.get("description") or (raw.get("_jobposting") or {}).get("description")
    description = description or raw.get("content_html") or ""

    return {
        "title": str(title).strip(),
        "company": company,
        "url": str(url).strip(),
        "location": location.strip(),
        "posted_date_text": str(raw.get("updated_at") or raw.get("createdAt") or "").strip(),
        "snippet": str(description)[:CAREER_PAGE_SNIPPET_CHARS].strip(),
        "source": f"career_page:ats_api:{ats_name}",
        "extraction_method": "ats_api",
        "detected_ats": ats_name,
    }


def _parse_personio_xml_jobs(xml_text: str, slug: str) -> list[dict]:
    """Personio's public feed is XML, not JSON — normalize to the same raw-dict
    shape _normalise_ats_job expects for the other ATS platforms."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)  # noqa: S314
    except ET.ParseError:
        return []
    jobs = []
    for position in root.findall("position"):
        job_id = (position.findtext("id") or "").strip()
        name = (position.findtext("name") or "").strip()
        office = (position.findtext("office") or "").strip()
        if not job_id or not name:
            continue
        jobs.append(
            {
                "title": name,
                "location": office,
                "url": f"https://{slug}.jobs.personio.de/job/{job_id}",
                "createdAt": (position.findtext("createdAt") or "").strip(),
            }
        )
    return jobs


import logging  # noqa: E402

logger = logging.getLogger(__name__)


def _raw_jobs_from_response(resp: requests.Response, ats_name: str, slug: str) -> list[dict]:
    """Extract the flat list of raw job dicts from an ATS API response."""
    if ats_name == "personio":
        # Personio's public feed is XML, not JSON.
        return _parse_personio_xml_jobs(resp.text, slug)
    try:
        data = resp.json()
    except ValueError:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "postings", "offers", "results", "content", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _fetch_ats_endpoint_jobs(
    slug: str,
    ats_name: str,
    api_url_template: str,
    title_filters: list[str],
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
    except Exception as exc:
        logger.debug("[career_pages] ATS API fetch failed (%s, %s): %s", ats_name, slug, exc)
        return []

    raw_jobs = _raw_jobs_from_response(resp, ats_name, slug)

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
