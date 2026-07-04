"""Rendering-based career page extraction (Playwright)."""

from __future__ import annotations

import logging
import subprocess

from job_hunter.config.loader import get_timeout
from job_hunter.sources.search import USER_AGENT, extract_jobs_from_html

logger = logging.getLogger(__name__)


def is_chromium_installed() -> bool:
    """Probe whether Playwright's chromium browser is downloaded and launchable."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def ensure_chromium_installed() -> bool:
    """Make sure Playwright's chromium browser is downloaded, installing it if not.

    Playwright is a core dependency, but the pip package alone doesn't ship the
    browser binary — `playwright install chromium` is a separate, idempotent
    download step. Runs it automatically so a first-time hunt doesn't silently
    degrade to zero browser-rendered results.
    """
    if is_chromium_installed():
        return True
    logger.info("[career_pages] chromium not ready; installing…")
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True)  # noqa: S603, S607
        return True
    except Exception as exc:
        logger.warning("[career_pages] playwright install chromium failed: %s", exc)
        return False


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
