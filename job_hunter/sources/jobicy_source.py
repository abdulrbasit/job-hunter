"""Jobicy remote jobs API source — no key required.

Free public API: https://jobicy.com/jobs-rss-feed
Up to 100 results per request. Supports documented geo slugs and tag filters.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

from job_hunter.core.api_budget import reserve_api_call
from job_hunter.core.config import ROOT, get_timeout, load_api_config
from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.source_config import jobicy_geo_slug

logger = logging.getLogger(__name__)

_API_URL = "https://jobicy.com/api/v2/remote-jobs"
_CACHE_PATH = Path(ROOT) / "outputs" / "state" / "jobicy_feed_cache.json"
_CACHE_TTL = timedelta(hours=1)


def _read_cache(geo: str) -> list[dict] | None:
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        entry = data.get(geo)
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        if datetime.now(UTC) - fetched_at <= _CACHE_TTL and isinstance(entry.get("jobs"), list):
            return entry["jobs"]
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def _write_cache(geo: str, jobs: list[dict]) -> None:
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8")) if _CACHE_PATH.exists() else {}
    except json.JSONDecodeError:
        data = {}
    data[geo] = {"fetched_at": datetime.now(UTC).isoformat(), "jobs": jobs}
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
        if not geo:
            logger.info("[jobicy] no documented geo for country=%s; skipping", params.country)
            return []
        jobs: list[JobPosting] = []

        raw_jobs = _read_cache(geo)
        if raw_jobs is None:
            if not reserve_api_call("jobicy"):
                return []

            api_params: dict = {"count": 100, "geo": geo}

            logger.info("[jobicy] fetching feed geo=%s", geo)

            try:
                resp = requests.get(_API_URL, params=api_params, timeout=timeout)
                resp.raise_for_status()
                raw_jobs = resp.json().get("jobs", [])
            except Exception as exc:
                logger.warning("[jobicy] request failed for geo=%s: %s", geo, exc)
                return []
            if isinstance(raw_jobs, list):
                _write_cache(geo, raw_jobs)

        if not isinstance(raw_jobs, list):
            return []

        for item in raw_jobs:
            if not isinstance(item, dict):
                continue
            job_title = str(item.get("jobTitle") or "")
            if not title_matches(job_title, params.job_titles, params.excluded_title_terms):
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
                    query=f"{' | '.join(params.job_titles[:3])} @ {params.region_key}",
                    region=params.region_key,
                )
            )

        logger.info("[jobicy] Complete: %d total jobs found", len(jobs))
        return jobs
