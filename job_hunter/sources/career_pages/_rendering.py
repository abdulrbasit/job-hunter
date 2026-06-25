"""Rendering-based career page extraction (Playwright, Lightpanda, Firecrawl)."""

from __future__ import annotations

import logging

from job_hunter.config.loader import get_timeout
from job_hunter.sources.search_providers import (
    USER_AGENT,
    extract_jobs_from_html,
    fetch_firecrawl_career_jobs,
    fetch_lightpanda_career_jobs,
)

logger = logging.getLogger(__name__)


def extract_from_rendered_html(
    career_url: str,
    company_name: str,
    title_filters: list[str],
    location: str = "",
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Render a JavaScript-heavy career page with Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("[career_pages] playwright not installed; skipping rendered extraction")
        return []

    url = career_url if "://" in career_url else f"https://{career_url}"
    pw_timeout_ms = int(get_timeout("playwright") * 1000)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, wait_until="networkidle", timeout=pw_timeout_ms)
                html = page.content()
                final_url = page.url or url
            finally:
                browser.close()
    except Exception as exc:
        logger.debug("[career_pages] Playwright render failed for %s: %s", career_url, exc)
        return []

    raw_jobs = extract_jobs_from_html(
        html,
        final_url,
        company_name,
        title_filters,
        location,
        "career_page:playwright",
        excluded_title_terms,
    )
    for job in raw_jobs:
        job["extraction_method"] = "playwright"
    return raw_jobs


def extract_from_lightpanda(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Render a public page with Lightpanda when the binary is available."""
    jobs = fetch_lightpanda_career_jobs(company, title_filters, excluded_title_terms)
    for job in jobs:
        job["extraction_method"] = "lightpanda"
    return jobs


def extract_from_firecrawl(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Scrape public pages through Firecrawl when key and budget are available."""
    jobs = fetch_firecrawl_career_jobs(company, title_filters, excluded_title_terms)
    for job in jobs:
        job["extraction_method"] = "firecrawl"
    return jobs


def extract_from_static_html(
    career_url: str,
    company_name: str,
    title_filters: list[str],
    location: str = "",
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch and parse static HTML to find job-detail links."""
    import requests

    url = career_url if "://" in career_url else f"https://{career_url}"
    timeout = get_timeout("ats_scraper")
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.debug("[career_pages] static HTML fetch failed for %s: %s", career_url, exc)
        return []

    raw_jobs = extract_jobs_from_html(
        resp.text,
        resp.url or url,
        company_name,
        title_filters,
        location,
        "career_page:static_html",
        excluded_title_terms,
    )
    for job in raw_jobs:
        job["extraction_method"] = "static_html"
    return raw_jobs
