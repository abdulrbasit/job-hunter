"""Bayt — Middle East/Gulf job board with a stable, no-key public HTML search.

Static HTTP only. Server-rendered listing pages (verified: /en/{country}/jobs/
and /en/{country}/jobs/{keyword}-jobs/ both return real job cards with no
auth wall), so no rendering fallback is needed here.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.constants import MAX_SAFE_PAGES_PER_SOURCE
from job_hunter.core.utils import strip_html, title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import terminal_http_status

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.bayt.com"

# Verified live (curl, 200 OK, real job cards) — Middle East/Gulf coverage only.
_COUNTRY_SLUGS: dict[str, str] = {
    "AE": "uae",
    "SA": "saudi-arabia",
    "QA": "qatar",
    "KW": "kuwait",
    "BH": "bahrain",
    "OM": "oman",
    "EG": "egypt",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_MAX_PAGES = MAX_SAFE_PAGES_PER_SOURCE
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _keyword_slug(title: str) -> str:
    return _SLUG_RE.sub("-", title.lower()).strip("-")


def _next_page_url(html: str, current_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", attrs={"rel": "next"}) or soup.find("a", attrs={"rel": "next"})
    href = link.get("href") if link else ""
    return urljoin(current_url, str(href)) if href else ""


def _parse_cards(
    html: str,
    title_filters: list[str],
    excluded_title_terms: list[str],
    region_name: str,
    title_query: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for card in soup.select("li[data-js-job]"):
        title_tag = card.select_one("h2 a") or card.find("a", attrs={"data-js-link": True})
        job_title = (title_tag.get("title") or title_tag.get_text(strip=True)) if title_tag else ""
        if not job_title:
            continue
        if not title_is_allowed(job_title, title_filters, excluded_title_terms):
            continue

        href = title_tag.get("href", "") if title_tag else ""
        if href and not href.startswith("http"):
            href = urljoin(_BASE_URL, href)

        company_tag = card.select_one(".job-company-location-wrapper a")
        company = company_tag.get_text(strip=True) if company_tag else ""

        location_tag = card.select_one(".job-company-location-wrapper .t-mute")
        job_location = ", ".join(s.get_text(strip=True) for s in location_tag.select("span")) if location_tag else ""

        date_tag = card.select_one(".jb-date")
        posted = date_tag.get_text(strip=True) if date_tag else ""

        desc_tag = card.select_one(".jb-descr")
        snippet = desc_tag.get_text(" ", strip=True) if desc_tag else ""
        snippet = re.sub(r"^Summary:\s*", "", snippet)

        jobs.append(
            {
                "title": job_title,
                "company": company,
                "url": href,
                "posted_date_text": posted,
                "location": job_location,
                "snippet": strip_html(snippet)[:3000],
                "source": "Bayt",
                "search_query": f"{title_query} @ {region_name}",
                "region": region_name,
            }
        )
    return jobs


def _to_posting(j: dict) -> JobPosting:
    return JobPosting(
        title=j["title"],
        company=j["company"],
        url=j["url"],
        posted_date_text=j["posted_date_text"],
        location=j["location"],
        snippet=j["snippet"],
        source=j["source"],
        search_query=j["search_query"],
        region=j["region"],
    )


class BaytSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "bayt"

    def is_enabled(self, api_config: dict) -> bool:
        config = (api_config or {}).get("http", {}).get("job_boards", {}).get("bayt", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch_title(self, title: str, url: str, params: SearchParams, timeout: int) -> tuple[list[JobPosting], bool]:
        """Fetch every page for one title. Returns (jobs, terminal_stop)."""
        jobs: list[JobPosting] = []
        for page in range(1, _MAX_PAGES + 1):
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=timeout)
                if resp.status_code == 429:
                    logger.warning("[bayt] rate limited; stopping source for this run")
                    return jobs, True
                if resp.status_code != 200 or len(resp.text) < 200:
                    break
                html = resp.text
            except Exception as exc:
                if terminal_http_status(exc):
                    logger.warning("[bayt] stopping after terminal HTTP error: %s", exc)
                    return jobs, True
                logger.debug("[bayt] request failed for %r in %s: %s", title, params.region_key, exc)
                break

            page_jobs = _parse_cards(html, params.job_titles, params.excluded_title_terms, params.region_key, title)
            logger.info("[bayt] page=%d found=%d", page, len(page_jobs))
            if not page_jobs:
                break
            jobs.extend(_to_posting(j) for j in page_jobs)

            next_url = _next_page_url(html, url)
            if not next_url or next_url == url:
                break
            url = next_url
        return jobs, False

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from Bayt. Only runs for Middle East regions in _COUNTRY_SLUGS."""
        iso = params.country.upper()
        country_slug = _COUNTRY_SLUGS.get(iso, "")
        if not country_slug:
            logger.debug("[bayt] skipped unsupported country=%r", params.country)
            return []

        source_config = get_api_config().get("http", {}).get("job_boards", {}).get("bayt", {}) or {}
        if not source_config.get("enabled", True):
            return []

        timeout = int(source_config.get("timeout_seconds") or get_timeout("job_boards"))
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            url = f"{_BASE_URL}/en/{country_slug}/jobs/{_keyword_slug(title)}-jobs/"
            title_jobs, terminal_stop = self._fetch_title(title, url, params, timeout)
            jobs.extend(title_jobs)
            logger.info("[bayt] +%d jobs for %r in %s", len(title_jobs), title, params.region_key)
            if terminal_stop:
                break

        logger.info("[bayt] Complete: %d total jobs", len(jobs))
        return jobs
