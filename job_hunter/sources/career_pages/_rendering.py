"""Rendering-based career page extraction (Playwright)."""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Callable

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


def extract_playwright_jobs_batch(  # noqa: C901
    companies: list[dict],
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
    *,
    on_result: Callable[[dict, list[dict], float], None] | None = None,
) -> list[tuple[dict, list[dict]]]:
    """Render several companies with one browser launch.

    A fresh context/page isolates each company. ``domcontentloaded`` plus a short,
    bounded settle replaces ``networkidle``, which commonly stalls on analytics
    and other long-lived requests.

    ``on_result`` receives this company's own render duration, timed from just
    before its page load — not from whenever the batch itself started. With a
    small worker pool and a large fallback queue (e.g. a 2,000-company
    career_pages.yml where most companies need this Playwright fallback),
    queue-wait time can dwarf actual per-company render time; a caller-side
    deadline check needs the latter, or it silently rejects companies that
    rendered fine but simply waited a long time for a free worker.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [(company, []) for company in companies]

    timeout_ms = int(get_timeout("playwright") * 1000)
    results: list[tuple[dict, list[dict]]] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                for company in companies:
                    context = browser.new_context(user_agent=USER_AGENT)
                    company_started_at = time.monotonic()
                    try:
                        page = context.new_page()
                        url = str(company.get("career_url") or "")
                        if "://" not in url:
                            url = f"https://{url}"
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                        page.wait_for_timeout(750)
                        jobs = extract_jobs_from_html(
                            page.content(),
                            page.url or url,
                            str(company.get("name") or ""),
                            title_filters,
                            str(company.get("location") or ""),
                            "career_page:playwright",
                            excluded_title_terms,
                        )
                        for job in jobs:
                            job["extraction_method"] = "playwright"
                        results.append((company, jobs))
                        if on_result:
                            on_result(company, jobs, time.monotonic() - company_started_at)
                    except Exception as exc:
                        logger.debug(
                            "[career_pages] Playwright render failed for %s: %s",
                            company.get("career_url"),
                            exc,
                        )
                        results.append((company, []))
                        if on_result:
                            on_result(company, [], time.monotonic() - company_started_at)
                    finally:
                        context.close()
            finally:
                browser.close()
    except Exception as exc:
        logger.debug("[career_pages] Playwright worker failed: %s", exc)
        known = {id(company) for company, _jobs in results}
        for company in companies:
            if id(company) in known:
                continue
            results.append((company, []))
            if on_result:
                on_result(company, [], 0.0)
    return results


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
