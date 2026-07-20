"""GulfTalent — Gulf region job board (UAE, Saudi Arabia, Qatar, Kuwait, Bahrain, Oman).

Tier 3: static HTTP only — tries several extraction strategies (cards, anchor
fallback, JSON-LD, embedded script data). No browser rendering: Playwright is
reserved for the company-hunt workflow only, never job-board scraping (GHA
timeout risk). Only fires for regions with a country code in the Gulf set —
GulfTalent has no worldwide/remote scope.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.constants import MAX_SAFE_PAGES_PER_SOURCE
from job_hunter.core.utils import strip_html, title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.career_pages._jsonld import extract_jsonld_jobs
from job_hunter.sources.search.fetchers import extract_jobs_from_html
from job_hunter.sources.source_config import terminal_http_status

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.gulftalent.com/jobs"
_BASE_URL = "https://www.gulftalent.com"

_GULF_CODES: frozenset[str] = frozenset({"AE", "SA", "QA", "KW", "BH", "OM"})

_COUNTRY_NAMES: dict[str, str] = {
    "AE": "United Arab Emirates",
    "SA": "Saudi Arabia",
    "QA": "Qatar",
    "KW": "Kuwait",
    "BH": "Bahrain",
    "OM": "Oman",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.gulftalent.com/",
}

# Code-owned page cap — GulfTalent is fragile behind anti-bot protection.
_MAX_PAGES = MAX_SAFE_PAGES_PER_SOURCE

# Best-effort embedded-script JSON scan: skip scripts too large to be a job payload.
_EMBEDDED_SCRIPT_MAX_CHARS = 200_000
_EMBEDDED_TITLE_KEYS = ("title", "jobTitle", "name")
_EMBEDDED_URL_KEYS = ("url", "link", "applyUrl", "detailUrl", "jobUrl")


def _make_posting(
    *, title: str, company: str, url: str, posted: str, location: str, snippet: str, title_query: str, region_name: str
) -> dict:
    return {
        "title": title,
        "company": company,
        "url": url,
        "posted_date_text": posted,
        "location": location,
        "snippet": strip_html(snippet)[:3000],
        "source": "GulfTalent",
        "search_query": f"{title_query} @ {region_name}",
        "region": region_name,
    }


def _parse_cards(
    html: str,
    title_filters: list[str],
    region_name: str,
    title_query: str,
) -> list[dict]:
    """Primary parser — GulfTalent's known job-listing card markup."""
    soup = BeautifulSoup(html, "html.parser")
    cards = (
        soup.find_all("div", {"class": re.compile(r"job.?listing|jobListing|job.?card", re.I)})
        or soup.find_all("article", {"class": re.compile(r"job", re.I)})
        or soup.select("li.job, div[data-job-id], div.job-item")
    )
    jobs = []
    for card in cards:
        title_tag = (
            card.find("a", {"class": re.compile(r"job.?title|jobTitle", re.I)}) or card.find("h2") or card.find("h3")
        )
        job_title = title_tag.get_text(strip=True) if title_tag else ""
        if not job_title:
            continue
        if not title_is_allowed(job_title, title_filters):
            continue

        company_tag = card.find(class_=re.compile(r"company|employer|organisation", re.I))
        company = company_tag.get_text(strip=True) if company_tag else ""

        link = title_tag if (title_tag and title_tag.name == "a") else card.find("a", href=True)
        href = link.get("href", "") if link else ""
        if href and not href.startswith("http"):
            href = urljoin(_BASE_URL, href)

        location_tag = card.find(class_=re.compile(r"location|city|area", re.I))
        job_location = location_tag.get_text(strip=True) if location_tag else ""

        date_tag = card.find(class_=re.compile(r"date|posted", re.I))
        posted = date_tag.get_text(strip=True) if date_tag else ""

        desc_tag = card.find(class_=re.compile(r"description|summary|snippet", re.I))
        snippet = desc_tag.get_text(strip=True) if desc_tag else ""

        jobs.append(
            _make_posting(
                title=job_title,
                company=company,
                url=href,
                posted=posted,
                location=job_location,
                snippet=snippet,
                title_query=title_query,
                region_name=region_name,
            )
        )
    return jobs


def _parse_anchor_fallback(
    html: str,
    base_url: str,
    title_filters: list[str],
    region_name: str,
    title_query: str,
) -> list[dict]:
    """Generic job-link anchor scan — reuses the same heuristic career-page fallback
    (title match + job-url shape) used across the rest of the sources package."""
    raw = extract_jobs_from_html(
        html,
        base_url,
        "",
        title_filters,
        "",
        "GulfTalent",
    )
    return [
        _make_posting(
            title=job["title"],
            company=job.get("company") or "",
            url=job["url"],
            posted=job.get("posted_date_text") or "",
            location="",
            snippet=job.get("snippet") or "",
            title_query=title_query,
            region_name=region_name,
        )
        for job in raw
        if job.get("title") and job.get("url")
    ]


def _parse_jsonld(
    html: str,
    base_url: str,
    title_filters: list[str],
    region_name: str,
    title_query: str,
) -> list[dict]:
    """schema.org JobPosting <script type="application/ld+json"> blocks, if present."""
    raw = extract_jsonld_jobs(html, base_url, "", title_filters=None)
    jobs = []
    for job in raw:
        if not title_is_allowed(job.get("title") or "", title_filters):
            continue
        jobs.append(
            _make_posting(
                title=job["title"],
                company=job.get("company") or "",
                url=job.get("url") or "",
                posted=job.get("posted_date_text") or "",
                location=job.get("location") or "",
                snippet=job.get("snippet") or "",
                title_query=title_query,
                region_name=region_name,
            )
        )
    return [j for j in jobs if j["url"]]


def _iter_embedded_dicts(value: object):
    """Depth-first walk of parsed JSON, yielding dicts that look like job records."""
    if isinstance(value, dict):
        if any(k in value for k in _EMBEDDED_TITLE_KEYS) and any(k in value for k in _EMBEDDED_URL_KEYS):
            yield value
        for v in value.values():
            yield from _iter_embedded_dicts(v)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_embedded_dicts(item)


def _parse_embedded_script(
    html: str,
    title_filters: list[str],
    region_name: str,
    title_query: str,
) -> list[dict]:
    """Best-effort scan of non-ld+json <script> blocks for an embedded jobs array
    (e.g. window.__INITIAL_STATE__ = {...}). Skips oversized scripts."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()
    for script in soup.find_all("script"):
        if script.get("type") == "application/ld+json" or script.get("src"):
            continue
        text = script.string or ""
        if not text or len(text) > _EMBEDDED_SCRIPT_MAX_CHARS:
            continue
        match = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if not match:
            continue
        try:
            payload = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            continue
        for record in _iter_embedded_dicts(payload):
            job_title = next((str(record[k]) for k in _EMBEDDED_TITLE_KEYS if record.get(k)), "")
            job_url = next((str(record[k]) for k in _EMBEDDED_URL_KEYS if record.get(k)), "")
            if not job_title or not job_url or job_url in seen:
                continue
            if not title_is_allowed(job_title, title_filters):
                continue
            seen.add(job_url)
            if not job_url.startswith("http"):
                job_url = urljoin(_BASE_URL, job_url)
            jobs.append(
                _make_posting(
                    title=job_title,
                    company=str(record.get("company") or record.get("companyName") or ""),
                    url=job_url,
                    posted=str(record.get("postedDate") or record.get("date") or ""),
                    location=str(record.get("location") or ""),
                    snippet=str(record.get("description") or record.get("snippet") or ""),
                    title_query=title_query,
                    region_name=region_name,
                )
            )
    return jobs


def _extract_jobs(
    html: str,
    base_url: str,
    title_filters: list[str],
    region_name: str,
    title_query: str,
) -> list[dict]:
    """Cascade through extraction strategies; stop at the first one that finds jobs."""
    for extractor in (
        lambda: _parse_cards(html, title_filters, region_name, title_query),
        lambda: _parse_anchor_fallback(html, base_url, title_filters, region_name, title_query),
        lambda: _parse_jsonld(html, base_url, title_filters, region_name, title_query),
        lambda: _parse_embedded_script(html, title_filters, region_name, title_query),
    ):
        jobs = extractor()
        if jobs:
            return jobs
    return []


def _next_page_url(html: str, current_url: str) -> str:
    """Follow the page's own declared next-page link instead of guessing a query param.

    Checks <link rel="next"> (head) first, then a body <a rel="next"> anchor —
    both are patterns verified against GulfTalent-style pagination fixtures.
    """
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", attrs={"rel": "next"}) or soup.find("a", attrs={"rel": "next"})
    href = link.get("href") if link else ""
    return urljoin(current_url, str(href)) if href else ""


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


class GulfTalentSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "gulftalent"

    def is_enabled(self, api_config: dict) -> bool:
        config = (api_config or {}).get("http", {}).get("job_boards", {}).get("gulftalent", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch_page(self, url: str, timeout: int) -> tuple[str, bool]:
        """Returns (html, terminal_stop)."""
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout)
            if resp.status_code == 429:
                logger.warning("[gulftalent] rate limited; stopping source for this run")
                return "", True
            if resp.status_code == 200 and len(resp.text) > 200:
                return resp.text, False
            return "", False
        except Exception as exc:
            if terminal_http_status(exc):
                logger.warning("[gulftalent] stopping after terminal HTTP error: %s", exc)
                return "", True
            logger.debug("[gulftalent] request failed for %s: %s", url, exc)
            return "", False

    def _fetch_static_pages(self, title: str, url: str, params: SearchParams, timeout: int) -> tuple[list[dict], bool]:
        """Follow pagination for one title. Returns (jobs, terminal_stop)."""
        title_jobs: list[dict] = []
        for page in range(1, _MAX_PAGES + 1):
            html, terminal_stop = self._fetch_page(url, timeout)
            if terminal_stop:
                return title_jobs, True
            if not html:
                logger.warning("[gulftalent] no HTML for %r in %s (page=%d)", title, params.region_key, page)
                break

            page_jobs = _extract_jobs(html, url, params.job_titles, params.region_key, title)
            logger.info("[gulftalent] page=%d found=%d", page, len(page_jobs))
            if not page_jobs:
                break
            title_jobs.extend(page_jobs)

            next_url = _next_page_url(html, url)
            if not next_url or next_url == url:
                break
            url = next_url
        return title_jobs, False

    def _fetch_title(self, title: str, params: SearchParams, timeout: int) -> tuple[list[JobPosting], bool]:
        country_name = _COUNTRY_NAMES.get(params.country.upper(), params.country)
        url = f"{_SEARCH_URL}?keyword={quote(title)}&location={quote(country_name)}"
        title_jobs, terminal_stop = self._fetch_static_pages(title, url, params, timeout)
        return [_to_posting(j) for j in title_jobs], terminal_stop

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from GulfTalent. Only runs for Gulf regions (AE, SA, QA, KW, BH, OM)."""
        iso = params.country.upper()
        if iso not in _GULF_CODES:
            return []

        source_config = get_api_config().get("http", {}).get("job_boards", {}).get("gulftalent", {}) or {}
        if not source_config.get("enabled", True):
            return []

        timeout = int(source_config.get("timeout_seconds") or get_timeout("job_boards"))
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            title_jobs, terminal_stop = self._fetch_title(title, params, timeout)
            jobs.extend(title_jobs)
            logger.info("[gulftalent] +%d jobs for %r in %s", len(title_jobs), title, params.region_key)
            if terminal_stop:
                break

        logger.info("[gulftalent] Complete: %d total jobs", len(jobs))
        return jobs
