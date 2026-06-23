"""Main extraction ladder coordinator for career pages."""

from __future__ import annotations

import logging

import requests

from job_hunter.core.config import get_timeout
from job_hunter.sources.search_providers import USER_AGENT, extract_jobs_from_html

logger = logging.getLogger(__name__)


def _fetch_html_safe(url: str) -> tuple[str, int]:
    """Fetch URL, return (html_text, status_code). Returns ('', 0) on error."""
    try:
        timeout = get_timeout("ats_scraper")
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        return resp.text, resp.status_code
    except Exception as exc:
        logger.debug("[career_pages] fetch failed for %s: %s", url, exc)
        return "", 0


def _try_sitemap_discovery(
    career_url: str,
    name: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    from job_hunter.sources.career_pages._sitemap import discover_via_sitemap

    return discover_via_sitemap(career_url, name, title_filters, excluded_title_terms)


def _try_static_html(
    html: str,
    base_url: str,
    name: str,
    title_filters: list[str],
    location: str,
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    raw_jobs = extract_jobs_from_html(
        html,
        base_url,
        name,
        title_filters,
        location,
        "career_page:static_html",
        excluded_title_terms,
    )
    for job in raw_jobs:
        job["extraction_method"] = "static_html"
    return raw_jobs


def _try_playwright(
    career_url: str,
    name: str,
    title_filters: list[str],
    location: str,
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    from job_hunter.sources.career_pages._rendering import extract_from_rendered_html

    return extract_from_rendered_html(career_url, name, title_filters, location, excluded_title_terms)
