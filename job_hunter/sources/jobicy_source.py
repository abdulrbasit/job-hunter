"""Jobicy remote jobs API source — no key required.

Free public API: https://jobicy.com/jobs-rss-feed
Up to 100 results per request. Supports documented geo slugs and tag filters.
"""

from __future__ import annotations

import logging

import requests

from job_hunter.core.api_budget import reserve_api_call
from job_hunter.core.config import get_timeout, load_api_config
from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import jobicy_geo_slug

logger = logging.getLogger(__name__)

_API_URL = "https://jobicy.com/api/v2/remote-jobs"


class JobicySource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "jobicy"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jobicy", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch remote jobs from Jobicy's free public API."""
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jobicy", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        geo = jobicy_geo_slug({"country": params.country, "location": params.location})
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            if not reserve_api_call("jobicy"):
                continue

            api_params: dict = {"count": 100, "tag": title}
            if geo:
                api_params["geo"] = geo

            logger.info("[jobicy] [%s] Searching for %r (geo=%r)", params.region_key, title, geo or "any")

            try:
                resp = requests.get(_API_URL, params=api_params, timeout=timeout)
                resp.raise_for_status()
                raw_jobs = resp.json().get("jobs", [])
            except Exception as exc:
                logger.warning("[jobicy] request failed for %r in %s: %s", title, params.region_key, exc)
                continue

            if not isinstance(raw_jobs, list):
                continue

            before = len(jobs)
            for item in raw_jobs:
                if not isinstance(item, dict):
                    continue
                job_title = str(item.get("jobTitle") or "")
                if not title_matches(job_title, params.job_titles, []):
                    continue
                description = strip_html(str(item.get("jobDescription") or ""))
                jobs.append(
                    JobPosting(
                        title=job_title,
                        company=str(item.get("companyName") or ""),
                        url=str(item.get("url") or ""),
                        posted=str(item.get("pubDate") or "")[:10],
                        location=str(item.get("jobGeo") or "Remote"),
                        snippet=description[:3000],
                        source="Jobicy",
                        query=f"{title} @ {params.region_key}",
                        region=params.region_key,
                    )
                )
            logger.info("[jobicy] +%d jobs for %r in %s", len(jobs) - before, title, params.region_key)

        logger.info("[jobicy] Complete: %d total jobs found", len(jobs))
        return jobs
