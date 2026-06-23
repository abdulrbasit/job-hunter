"""Search-backed ATS and AI discovery for scraper runs."""

from __future__ import annotations

import logging

from job_hunter.models import JobPosting
from job_hunter.sources.ai_web_search import fetch_ai_web_search_jobs
from job_hunter.sources.scraper._stats import ScrapeStats
from job_hunter.sources.search_providers import BraveProvider, discover_ats_jobs_by_search

logger = logging.getLogger(__name__)


def brave_search(query: str, region_config: dict, count: int | None = None) -> list[dict]:
    count = count or 10
    try:
        results = BraveProvider().search(query, region_config, count=count)
    except Exception as e:
        logger.error("[scraper] Error during Brave Search: %s", e)
        raise
    return [
        {
            "url": result.url,
            "title": result.title,
            "description": result.description,
            "source": result.source,
        }
        for result in results
    ]


def _collect_discovery(
    discover_fn,
    stat_key: str,
    warning_msg: str,
    stats: ScrapeStats,
    add_job,
) -> None:
    stats.record(stat_key, attempted=1)
    try:
        jobs = list(discover_fn())
        stats.record(stat_key, returned=len(jobs))
        accepted = 0
        for job in jobs:
            if add_job(JobPosting.from_dict(job), cache_candidate=True):
                accepted += 1
        stats.record(stat_key, accepted=accepted, skipped=len(jobs) - accepted)
    except Exception as e:
        stats.record(stat_key, failed=1)
        logger.warning(warning_msg, e)


def collect_ats_discovery(
    title_filters: list[str],
    enabled_regions: dict[str, dict],
    excluded_title_terms: list[str],
    disabled: set[str],
    stats: ScrapeStats,
    add_job,
) -> None:
    _collect_discovery(
        lambda: discover_ats_jobs_by_search(
            title_filters,
            enabled_regions,
            excluded_title_terms,
            disabled=disabled,
        ),
        "ats_search_discovery",
        "[scraper] ATS search discovery failed: %s",
        stats,
        add_job,
    )


def collect_ai_web_search(
    title_filters: list[str],
    enabled_regions: dict[str, dict],
    stats: ScrapeStats,
    add_job,
) -> None:
    _collect_discovery(
        lambda: fetch_ai_web_search_jobs(title_filters, enabled_regions),
        "ai_web_search",
        "[scraper] AI web search failed: %s",
        stats,
        add_job,
    )
