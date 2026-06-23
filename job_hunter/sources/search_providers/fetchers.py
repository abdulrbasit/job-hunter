"""Career-page fetchers: static HTTP, Lightpanda, Firecrawl, Playwright."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_hunter.core.api_budget import reserve_api_call
from job_hunter.core.config import FIRECRAWL_API_KEY, get_timeout, load_api_config
from job_hunter.core.utils import title_matches
from job_hunter.sources.search_providers._constants import USER_AGENT
from job_hunter.sources.search_providers._url_utils import (
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
                "posted": "",
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


def _jobs_from_markdown_links(
    markdown: str,
    base_url: str,
    company_name: str,
    title_filters: list[str],
    location: str,
    source: str,
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()
    for match in re.finditer(r"\[([^\]]{2,160})\]\((https?://[^)\s]+|/[^)\s]+)\)", markdown):
        text = " ".join(match.group(1).split())
        url = urljoin(base_url, match.group(2))
        haystack = f"{text} {url}"
        if not _looks_like_job_url(url) and not title_matches(haystack, title_filters, excluded_title_terms):
            continue
        if not title_matches(text or haystack, title_filters, excluded_title_terms):
            continue
        if not _location_match(markdown[:4000], location):
            continue
        canonical = canonicalize_url(url)
        if canonical in seen:
            continue
        seen.add(canonical)
        jobs.append(
            {
                "title": text,
                "company": company_name,
                "url": url,
                "posted": "",
                "snippet": text,
                "source": source,
            }
        )
    return jobs


def fetch_lightpanda_career_jobs(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    binary = shutil.which("lightpanda")
    if not binary:
        logger.debug("[search] lightpanda binary not found; skipping career render")
        return []

    url = _with_scheme(company["career_url"])
    timeout_seconds = int(load_api_config().get("http", {}).get("lightpanda", {}).get("timeout_seconds", 8))
    timeout_ms = timeout_seconds * 1000
    try:
        completed = subprocess.run(  # noqa: S603
            [
                binary,
                "fetch",
                "--dump",
                "html",
                "--log_level",
                "error",
                "--http_timeout",
                str(timeout_ms),
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 2,
            check=False,
        )
    except Exception as exc:
        logger.debug("[search] Lightpanda failed for %s: %s", url, exc)
        return []
    if completed.returncode != 0 or not completed.stdout:
        logger.debug("[search] Lightpanda returned no content for %s", url)
        return []
    return extract_jobs_from_html(
        completed.stdout,
        url,
        company["name"],
        title_filters,
        company.get("location", ""),
        "Lightpanda career page",
        excluded_title_terms,
    )


def fetch_firecrawl_career_jobs(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    api_key = FIRECRAWL_API_KEY
    if not api_key:
        logger.debug("[search] FIRECRAWL_API_KEY not set; skipping cloud scrape")
        return []
    if not reserve_api_call("firecrawl"):
        return []

    cfg = load_api_config().get("http", {}).get("firecrawl", {}) or {}
    timeout_seconds = int(cfg.get("timeout_seconds", 20))
    url = _with_scheme(company["career_url"])
    try:
        resp = requests.post(
            cfg.get("api_url", "https://api.firecrawl.dev/v2/scrape"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
                "timeout": timeout_seconds * 1000,
                "parsers": [],
            },
            timeout=timeout_seconds + 5,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.debug("[search] Firecrawl failed for %s: %s", url, exc)
        return []

    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    markdown = str((data or {}).get("markdown") or "")
    if not markdown:
        return []
    return _jobs_from_markdown_links(
        markdown,
        url,
        company["name"],
        title_filters,
        company.get("location", ""),
        "Firecrawl career page",
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
