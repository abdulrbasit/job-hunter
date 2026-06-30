"""Per-platform bulk job-list fetchers for ATS slug-cache queries.

All endpoints are public and require no authentication. Each function returns
minimal job dicts: {title, url, location, snippet}. Company name is NOT
included — callers derive it from the slug.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def _get_json(url: str, timeout: int, **params: str) -> dict | list | None:
    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS, params=params or None)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.debug("[ats_apis] GET %s failed: %s", url, exc)
        return None


def _fetch_greenhouse(slug: str, timeout: int) -> list[dict]:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout, content="true")
    if not isinstance(data, dict):
        return []
    jobs = []
    for j in data.get("jobs") or []:
        url = j.get("absolute_url", "")
        title = j.get("title", "")
        if not url or not title:
            continue
        jobs.append({"title": title, "url": url, "location": (j.get("location") or {}).get("name", ""), "snippet": ""})
    return jobs


def _fetch_lever(slug: str, timeout: int) -> list[dict]:
    data = _get_json(f"https://api.lever.co/v0/postings/{slug}", timeout, mode="json")
    if not isinstance(data, list):
        return []
    jobs = []
    for j in data:
        url = j.get("hostedUrl", "")
        title = j.get("text", "")
        if not url or not title:
            continue
        loc = (j.get("categories") or {}).get("location", "")
        jobs.append({"title": title, "url": url, "location": loc, "snippet": j.get("descriptionPlain", "")[:2000]})
    return jobs


def _fetch_ashby(slug: str, timeout: int) -> list[dict]:
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout)
    if not isinstance(data, dict):
        return []
    jobs = []
    for j in data.get("jobPostings") or []:
        url = j.get("jobPostingUrl", "")
        title = j.get("title", "")
        if not url or not title:
            continue
        jobs.append({"title": title, "url": url, "location": j.get("locationName", ""), "snippet": ""})
    return jobs


def _fetch_smartrecruiters(slug: str, timeout: int) -> list[dict]:
    data = _get_json(
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
        timeout,
        status="PUBLISHED",
    )
    if not isinstance(data, dict):
        return []
    jobs = []
    for j in data.get("content") or []:
        ref = j.get("id", "")
        title = j.get("name", "")
        if not ref or not title:
            continue
        url = f"https://jobs.smartrecruiters.com/{slug}/{ref}"
        loc_data = j.get("location") or {}
        loc = ", ".join(filter(None, [loc_data.get("city", ""), loc_data.get("country", "")]))
        jobs.append({"title": title, "url": url, "location": loc, "snippet": ""})
    return jobs


def _fetch_workable(slug: str, timeout: int) -> list[dict]:
    data = _get_json(
        f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
        timeout,
        details="true",
        status="published",
    )
    if not isinstance(data, dict):
        return []
    jobs = []
    for j in data.get("jobs") or []:
        shortcode = j.get("shortcode", "")
        title = j.get("title", "")
        if not shortcode or not title:
            continue
        url = f"https://apply.workable.com/{slug}/j/{shortcode}"
        loc = (j.get("location") or {}).get("city", "")
        jobs.append({"title": title, "url": url, "location": loc, "snippet": ""})
    return jobs


def _fetch_personio(slug: str, timeout: int) -> list[dict]:
    data = _get_json(f"https://{slug}.jobs.personio.de/api/v1/jobs", timeout)
    if not isinstance(data, list):
        return []
    jobs = []
    for j in data:
        job_id = j.get("id", "")
        title = j.get("name", "")
        if not job_id or not title:
            continue
        url = f"https://{slug}.jobs.personio.de/job/{job_id}"
        office = (j.get("office") or {}).get("name", "")
        jobs.append({"title": title, "url": url, "location": office, "snippet": ""})
    return jobs


def _fetch_breezy(slug: str, timeout: int) -> list[dict]:
    data = _get_json(f"https://{slug}.breezy.hr/json", timeout)
    if not isinstance(data, list):
        return []
    jobs = []
    for j in data:
        job_id = j.get("_id", "")
        title = j.get("name", "")
        if not job_id or not title:
            continue
        url = f"https://{slug}.breezy.hr/p/{job_id}"
        loc = (j.get("location") or {}).get("name", "")
        jobs.append({"title": title, "url": url, "location": loc, "snippet": ""})
    return jobs


def _fetch_recruitee(slug: str, timeout: int) -> list[dict]:
    data = _get_json(f"https://{slug}.recruitee.com/api/offers", timeout)
    if not isinstance(data, dict):
        return []
    jobs = []
    for j in data.get("offers") or []:
        offer_slug = j.get("slug", "")
        title = j.get("title", "")
        if not offer_slug or not title:
            continue
        url = f"https://{slug}.recruitee.com/o/{offer_slug}"
        jobs.append({"title": title, "url": url, "location": j.get("city", ""), "snippet": ""})
    return jobs


_FETCHERS: dict[str, Callable[[str, int], list[dict]]] = {
    "greenhouse": _fetch_greenhouse,
    "lever": _fetch_lever,
    "ashby": _fetch_ashby,
    "smartrecruiters": _fetch_smartrecruiters,
    "workable": _fetch_workable,
    "personio": _fetch_personio,
    "breezy": _fetch_breezy,
    "recruitee": _fetch_recruitee,
}


def fetch_platform_jobs(platform: str, slug: str, timeout: int) -> list[dict]:
    """Fetch all published jobs for a company slug on a given ATS platform."""
    fn = _FETCHERS.get(platform)
    if fn is None:
        return []
    try:
        return fn(slug, timeout)
    except Exception as exc:
        logger.debug("[ats_apis] %s/%s failed: %s", platform, slug, exc)
        return []
