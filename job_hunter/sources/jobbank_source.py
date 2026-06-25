"""Job Bank Canada (jobbank.gc.ca) — Canadian government job portal.

Free, no API key required. HTML scraping with BeautifulSoup.
Only fires for regions with country == "CA".
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from job_hunter.config.loader import get_timeout, load_api_config
from job_hunter.core.utils import title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import terminal_http_status

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.jobbank.gc.ca/jobsearch/jobsearch"
_BASE_URL = "https://www.jobbank.gc.ca"
_JSESSIONID_RE = re.compile(r";jsessionid=[^?#]*")
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-CA,en;q=0.9",
}


class JobBankSource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "jobbank"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jobbank", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from Job Bank Canada by scraping the HTML search results.

        Only runs for Canadian regions (country == CA).
        """
        if params.country.upper() != "CA":
            return []

        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jobbank", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        location = params.location or "Canada"
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            try:
                resp = requests.get(
                    _SEARCH_URL,
                    params={
                        "searchstring": title,
                        "locationstring": location,
                        "action": "search",
                        "lang": "eng",
                    },
                    headers=_HEADERS,
                    timeout=timeout,
                )
                resp.raise_for_status()
                html = resp.text
            except Exception as exc:
                logger.warning("[jobbank] failed for %r in %s: %s", title, params.region_key, exc)
                if terminal_http_status(exc):
                    return jobs
                continue

            soup = BeautifulSoup(html, "html.parser")
            # JobBank renders each job as <article class="action-buttons" id="article-{id}">
            articles = soup.select("article.action-buttons[id^='article-']")
            if not articles:
                articles = soup.find_all("article")

            before = len(jobs)
            for article in articles:
                title_tag = (
                    article.find("span", {"class": re.compile(r"noctitle|jobtitle", re.I)})
                    or article.find("h3")
                    or article.find("h2")
                )
                job_title = title_tag.get_text(strip=True) if title_tag else ""
                if not job_title:
                    continue
                if not title_matches(job_title, params.job_titles, []):
                    continue

                company_tag = article.find(class_=re.compile(r"business|company|employer", re.I))
                company = company_tag.get_text(strip=True) if company_tag else ""

                link_tag = article.find("a", href=True)
                href = link_tag["href"] if link_tag else ""
                href = _JSESSIONID_RE.sub("", href)
                if href and not href.startswith("http"):
                    href = _BASE_URL + href

                location_tag = article.find(class_=re.compile(r"location|city|region", re.I))
                job_location = location_tag.get_text(strip=True) if location_tag else location

                date_tag = article.find(class_=re.compile(r"date|posted", re.I))
                posted = date_tag.get_text(strip=True) if date_tag else ""

                jobs.append(
                    JobPosting(
                        title=job_title,
                        company=company,
                        url=href,
                        posted=posted,
                        location=job_location,
                        snippet="",
                        source="JobBank Canada",
                        query=f"{title} @ {params.region_key}",
                        region=params.region_key,
                    )
                )
            logger.info("[jobbank] +%d jobs for %r in %s", len(jobs) - before, title, params.region_key)

        logger.info("[jobbank] Complete: %d total jobs", len(jobs))
        return jobs
