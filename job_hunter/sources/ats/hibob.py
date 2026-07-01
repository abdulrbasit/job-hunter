from __future__ import annotations

import logging
import re

from job_hunter.config.loader import get_api_config
from job_hunter.core.utils import location_matches, title_matches

logger = logging.getLogger(__name__)


def fetch_hibob_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """
    Scrape a HiBob career page with Playwright (JS-rendered — no public API).

    Loads the listing page, extracts all job links (UUID-style hrefs), and
    returns jobs with empty snippets. The orchestrator enriches these via
    fetch_jd before validation and scoring.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(f"[hibob] playwright not installed; cannot scrape {slug}.careers.hibob.com")
        return []

    career_url = f"https://{slug}.careers.hibob.com"
    # HiBob job URLs contain a UUID: /jobs/<8-4-4-4-12 hex>
    uuid_re = re.compile(
        r"/jobs/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        re.IGNORECASE,
    )

    raw_links: dict[str, tuple[str, str]] = {}  # url -> (title text, location text)
    ats_config = get_api_config().get("http", {}).get("ats_scraper", {}) or {}
    playwright_timeout = int(ats_config.get("hibob_playwright_timeout_seconds", 25) * 1000)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(career_url, wait_until="networkidle", timeout=playwright_timeout)
                for anchor in page.query_selector_all("a"):
                    href = anchor.get_attribute("href") or ""
                    if not uuid_re.search(href):
                        continue
                    if not href.startswith("http"):
                        href = f"https://{slug}.careers.hibob.com{href}"
                    title_text = (anchor.text_content() or "").strip()
                    if href not in raw_links and title_text:
                        loc_el = anchor.query_selector("[class*='location'], [class*='Location']")
                        location_text = (loc_el.text_content() or "").strip() if loc_el else ""
                        raw_links[href] = (title_text, location_text)
            finally:
                browser.close()
    except Exception as e:
        logger.warning(f"[hibob] Playwright failed for {career_url}: {e}")
        return []

    jobs = []
    for url, (title, location) in raw_links.items():
        if not title_matches(title, title_filters, excluded_title_terms):
            continue
        if location_filter and location and not location_matches(location, location_filter):
            continue
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted_date_text": "",
                "location": location,
                # snippet intentionally empty - enriched by orchestrator._enrich_snippets
                "snippet": "",
                "source": "HiBob",
            }
        )

    logger.info(f"[hibob] {slug}: {len(jobs)} matching jobs (from {len(raw_links)} total listings)")
    return jobs
