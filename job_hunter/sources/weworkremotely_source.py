"""We Work Remotely RSS source — no key required.

Public RSS feed: https://weworkremotely.com/remote-jobs.rss
Uses stdlib xml.etree.ElementTree — no extra dependency.
WWR item titles are formatted as "Company Name: Job Title".
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from job_hunter.core.config import get_timeout, load_api_config
from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter

logger = logging.getLogger(__name__)

_RSS_URL = "https://weworkremotely.com/remote-jobs.rss"


def _parse_rfc2822(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


class WeWorkRemotelySource(JobSourceAdapter):
    global_feed = True

    @property
    def source_name(self) -> str:
        return "weworkremotely"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("weworkremotely", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch remote jobs from We Work Remotely's public RSS feed."""
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("weworkremotely", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))

        logger.info("[weworkremotely] Fetching RSS feed")
        try:
            resp = requests.get(_RSS_URL, timeout=timeout)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)  # noqa: S314
        except Exception as exc:
            logger.warning("[weworkremotely] request/parse failed: %s", exc)
            return []

        jobs: list[JobPosting] = []
        for item in root.iter("item"):
            raw_title = (item.findtext("title") or "").strip()
            # WWR titles: "Company Name: Job Title"
            if ": " in raw_title:
                company, job_title = raw_title.split(": ", 1)
                company = company.strip()
                job_title = job_title.strip()
            else:
                company = ""
                job_title = raw_title

            if not title_matches(job_title, params.job_titles, []):
                continue

            url = (item.findtext("link") or "").strip()
            pub_date = _parse_rfc2822(item.findtext("pubDate") or "")
            description = strip_html(item.findtext("description") or "")

            jobs.append(
                JobPosting(
                    title=job_title,
                    company=company,
                    url=url,
                    posted=pub_date,
                    location="Remote",
                    snippet=description[:3000],
                    source="WeWorkRemotely",
                    query=job_title,
                    region=params.region_key,
                )
            )

        logger.info("[weworkremotely] %d jobs matched after filtering", len(jobs))
        return jobs
