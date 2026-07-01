"""GulfTalent — Gulf region job board (UAE, Saudi Arabia, Qatar, Kuwait, Bahrain, Oman).

Tier 3: requests with headers first; falls back to Playwright if the response is blocked.
Only fires for regions with country code in the Gulf set.
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
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


def _parse_cards(
    html: str,
    title_filters: list[str],
    excluded_title_terms: list[str],
    region_name: str,
    title_query: str,
) -> list[dict]:
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
        if not title_matches(job_title, title_filters, excluded_title_terms):
            continue

        company_tag = card.find(class_=re.compile(r"company|employer|organisation", re.I))
        company = company_tag.get_text(strip=True) if company_tag else ""

        link = title_tag if (title_tag and title_tag.name == "a") else card.find("a", href=True)
        href = link.get("href", "") if link else ""
        if href and not href.startswith("http"):
            href = _BASE_URL + href

        location_tag = card.find(class_=re.compile(r"location|city|area", re.I))
        job_location = location_tag.get_text(strip=True) if location_tag else ""

        date_tag = card.find(class_=re.compile(r"date|posted", re.I))
        posted = date_tag.get_text(strip=True) if date_tag else ""

        desc_tag = card.find(class_=re.compile(r"description|summary|snippet", re.I))
        snippet = strip_html(desc_tag.get_text(strip=True) if desc_tag else "")

        jobs.append(
            {
                "title": job_title,
                "company": company,
                "url": href,
                "posted_date_text": posted,
                "location": job_location,
                "snippet": snippet[:3000],
                "source": "GulfTalent",
                "search_query": f"{title_query} @ {region_name}",
                "region": region_name,
            }
        )
    return jobs


class GulfTalentSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "gulftalent"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = get_api_config().get("http", {}).get("job_boards", {}).get("gulftalent", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from GulfTalent (static HTTP only).

        Only runs for Gulf regions (AE, SA, QA, KW, BH, OM).
        """
        iso = params.country.upper()
        if iso not in _GULF_CODES:
            return []

        source_cfg = get_api_config().get("http", {}).get("job_boards", {}).get("gulftalent", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        country_name = _COUNTRY_NAMES.get(iso, iso)
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            req_params = {"keyword": title, "location": country_name}
            html = ""
            try:
                resp = requests.get(
                    _SEARCH_URL,
                    params=req_params,
                    headers=_HEADERS,
                    timeout=timeout,
                )
                if resp.status_code == 429:
                    logger.warning("[gulftalent] rate limited; stopping source for this run")
                    return jobs
                if resp.status_code == 200 and len(resp.text) > 200:
                    html = resp.text
            except Exception as exc:
                if terminal_http_status(exc):
                    logger.warning("[gulftalent] stopping after terminal HTTP error: %s", exc)
                    return jobs
                logger.debug("[gulftalent] requests failed for %r in %s: %s", title, params.region_key, exc)

            if not html:
                logger.warning("[gulftalent] no HTML for %r in %s", title, params.region_key)
                return jobs

            before = len(jobs)
            raw_jobs = _parse_cards(html, params.job_titles, [], params.region_key, title)
            for j in raw_jobs:
                jobs.append(
                    JobPosting(
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
                )
            logger.info("[gulftalent] +%d jobs for %r in %s", len(jobs) - before, title, params.region_key)

        logger.info("[gulftalent] Complete: %d total jobs", len(jobs))
        return jobs
