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

from job_hunter.core.utils import strip_html, title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import job_board_enabled, job_board_timeout

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

    def is_enabled(self, api_config: dict) -> bool:
        config = (api_config or {}).get("http", {}).get("job_boards", {}).get("weworkremotely", {}) or {}
        return bool(config.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch remote jobs from We Work Remotely's public RSS feed."""
        if not job_board_enabled("weworkremotely"):
            return []

        timeout = job_board_timeout("weworkremotely")

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

            if not title_is_allowed(job_title, params.job_titles):
                continue

            url = (item.findtext("link") or "").strip()
            pub_date = _parse_rfc2822(item.findtext("pubDate") or "")
            description = strip_html(item.findtext("description") or "")
            # The feed carries real structured location fields — use those instead
            # of guessing from description text.
            region_field = (item.findtext("region") or "").strip()
            country_field = (item.findtext("country") or "").strip()
            restrictions = [v for v in (region_field, country_field) if v]

            jobs.append(
                JobPosting(
                    title=job_title,
                    company=company,
                    url=url,
                    posted_date_text=pub_date,
                    location=country_field or region_field or "Remote",
                    snippet=description[:3000],
                    source="WeWorkRemotely",
                    search_query=job_title,
                    region=params.region_key,
                    location_restrictions=restrictions,
                )
            )

        logger.info("[weworkremotely] %d jobs matched after filtering", len(jobs))
        return jobs
