"""Career-page fetchers: static HTTP, Playwright."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_hunter.config.loader import get_timeout
from job_hunter.core.utils import title_matches
from job_hunter.sources.search._constants import USER_AGENT
from job_hunter.sources.search._url_utils import (
    _location_match,
    _looks_like_job_url,
    _with_scheme,
    canonicalize_url,
)

logger = logging.getLogger(__name__)


def extract_jobs_from_html(
    html: str,
    base_url: str,
    company_name: str,
    title_filters: list[str],
    location: str,
    source: str,
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href"))
        url = urljoin(base_url, href)
        text = " ".join(anchor.get_text(" ", strip=True).split())
        context = " ".join(anchor.parent.get_text(" ", strip=True).split() if anchor.parent else text)
        haystack = f"{text} {href} {context}"

        title_text = text or next((t for t in title_filters if t.lower() in haystack.lower()), "")

        if not _looks_like_job_url(url) and not title_matches(
            title_text or haystack, title_filters, excluded_title_terms
        ):
            continue
        if not title_matches(title_text or haystack, title_filters, excluded_title_terms):
            continue
        if not _location_match(haystack, location):
            continue
        canonical = canonicalize_url(url)
        if canonical in seen:
            continue

        seen.add(canonical)
        jobs.append(
            {
                "title": text or next((t for t in title_filters if t.lower() in haystack.lower()), "Job"),
                "company": company_name,
                "url": url,
                "posted_date_text": "",
                "snippet": context or text,
                "source": source,
            }
        )

    return jobs


def fetch_static_career_jobs(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    url = _with_scheme(company["career_url"])
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=get_timeout("ats_scraper"),
        allow_redirects=True,
    )
    resp.raise_for_status()
    if not isinstance(resp.text, str):
        return []
    return extract_jobs_from_html(
        resp.text,
        resp.url or url,
        company["name"],
        title_filters,
        company.get("location", ""),
        "HTTP career page",
        excluded_title_terms,
    )


def fetch_playwright_career_jobs(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("[search] playwright not installed; skipping career render")
        return []

    url = _with_scheme(company["career_url"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            pw_timeout = int(get_timeout("playwright") * 1000)
            page.goto(url, wait_until="networkidle", timeout=pw_timeout)
            html = page.content()
            return extract_jobs_from_html(
                html,
                page.url or url,
                company["name"],
                title_filters,
                company.get("location", ""),
                "Playwright career page",
                excluded_title_terms,
            )
        finally:
            browser.close()
