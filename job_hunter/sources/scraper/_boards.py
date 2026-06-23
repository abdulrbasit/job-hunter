"""Global board dispatch for source-first scraping."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from job_hunter.models import JobPosting
from job_hunter.sources._policy import make_job_filter
from job_hunter.sources.adzuna_source import AdzunaSource
from job_hunter.sources.arbeitsagentur_source import ArbeitsagenturSource
from job_hunter.sources.careerjet_source import CareerjetSource
from job_hunter.sources.glints_source import GlintsSource
from job_hunter.sources.gulftalent_source import GulfTalentSource
from job_hunter.sources.himalayas_source import HimalayasSource
from job_hunter.sources.job_boards import ArbeitnowSource, JSearchSource
from job_hunter.sources.jobbank_source import JobBankSource
from job_hunter.sources.jobicy_source import JobicySource
from job_hunter.sources.jobspy_source import JobSpySource
from job_hunter.sources.jobstreet_source import JobStreetSource
from job_hunter.sources.jooble_source import JoobleSource
from job_hunter.sources.mycareersfuture_source import MyCareersFutureSource
from job_hunter.sources.reed_source import ReedSource
from job_hunter.sources.remoteok_source import RemoteOKSource
from job_hunter.sources.remotive_source import RemotiveSource
from job_hunter.sources.scraper._config import enabled_regions as resolve_enabled_regions
from job_hunter.sources.scraper._config import load_search_config
from job_hunter.sources.scraper._discovery import collect_ai_web_search, collect_ats_discovery
from job_hunter.sources.scraper._stats import ScrapeStats
from job_hunter.sources.search_providers import all_providers_exhausted
from job_hunter.sources.search_providers.preflight import probe_job_sources, probe_search_providers
from job_hunter.sources.search_providers.router import set_run_disabled
from job_hunter.sources.the_muse_source import TheMuseSource
from job_hunter.sources.weworkremotely_source import WeWorkRemotelySource
from job_hunter.sources.workingnomads_source import WorkingNomadsSource
from job_hunter.tracking.discovery_cache import (
    load_cached_candidate_urls,
    save_cached_candidate_urls,
)

logger = logging.getLogger(__name__)


def _source_available(name: str, source_preflight: dict, source_skip_logged: set[str]) -> bool:
    result = source_preflight.get(name)
    if result is None or result.status == "ok":
        return True
    if name not in source_skip_logged:
        source_skip_logged.add(name)
        logger.info(
            "[preflight] %s: disabled for this run (%s%s)",
            name,
            result.status,
            f": {result.reason}" if result.reason else "",
        )
    return False


def _collect_source(
    name: str,
    fetcher: Callable[[], list[Any]],
    stats: ScrapeStats,
    add_job,
    source_preflight: dict,
    source_skip_logged: set[str],
    *,
    cache_candidate: bool = True,
) -> None:
    stats.record(name, attempted=1)
    if not _source_available(name, source_preflight, source_skip_logged):
        return
    try:
        postings = fetcher()
        stats.record(name, returned=len(postings))
        accepted = 0
        for jp in postings:
            if add_job(jp, cache_candidate=cache_candidate):
                accepted += 1
        stats.record(name, accepted=accepted, skipped=len(postings) - accepted)
    except Exception as e:
        stats.record(name, failed=1)
        logger.warning("[scraper] %s failed: %s", name, e)


def collect_board_sources(
    title_filters: list[str],
    enabled_regions: dict[str, dict],
    config: dict,
    stats: ScrapeStats,
    add_job,
    source_preflight: dict,
    source_skip_logged: set[str],
) -> None:
    sources: list[tuple[str, Callable[[], list[Any]]]] = [
        ("jobspy", lambda: JobSpySource().fetch(title_filters, enabled_regions, config)),
        ("himalayas", lambda: HimalayasSource().fetch(title_filters, enabled_regions, config)),
        ("remotive", lambda: RemotiveSource().fetch(title_filters, enabled_regions, config)),
        ("the_muse", lambda: TheMuseSource().fetch(title_filters, enabled_regions, config)),
        ("jobicy", lambda: JobicySource().fetch(title_filters, enabled_regions, config)),
        ("remoteok", lambda: RemoteOKSource().fetch(title_filters, enabled_regions, config)),
        (
            "weworkremotely",
            lambda: WeWorkRemotelySource().fetch(title_filters, enabled_regions, config),
        ),
        (
            "mycareersfuture",
            lambda: MyCareersFutureSource().fetch(title_filters, enabled_regions, config),
        ),
        ("jobbank", lambda: JobBankSource().fetch(title_filters, enabled_regions, config)),
        ("glints", lambda: GlintsSource().fetch(title_filters, enabled_regions, config)),
        ("gulftalent", lambda: GulfTalentSource().fetch(title_filters, enabled_regions, config)),
        ("jobstreet", lambda: JobStreetSource().fetch(title_filters, enabled_regions, config)),
        ("jooble", lambda: JoobleSource().fetch(title_filters, enabled_regions, config)),
        (
            "arbeitsagentur",
            lambda: ArbeitsagenturSource().fetch(title_filters, enabled_regions, config),
        ),
        ("arbeitnow", lambda: ArbeitnowSource().fetch(title_filters, enabled_regions, config)),
        ("jsearch", lambda: JSearchSource().fetch(title_filters, enabled_regions, config)),
        ("adzuna", lambda: AdzunaSource().fetch(title_filters, enabled_regions, config)),
        ("reed", lambda: ReedSource().fetch(title_filters, enabled_regions, config)),
        ("careerjet", lambda: CareerjetSource().fetch(title_filters, enabled_regions, config)),
        (
            "workingnomads",
            lambda: WorkingNomadsSource().fetch(title_filters, enabled_regions, config),
        ),
    ]
    for name, fetcher in sources:
        _collect_source(
            name,
            fetcher,
            stats,
            add_job,
            source_preflight,
            source_skip_logged,
            cache_candidate=False,
        )


def scrape(region: str | None = None, *, depth: str = "standard") -> list[JobPosting]:
    config = load_search_config()
    stats = ScrapeStats()

    run_disabled = probe_search_providers()
    set_run_disabled(run_disabled)
    logger.info("[scraper] depth=%s", depth)

    title_filters = config.get("job_titles", []) or []
    excluded_title_terms = (config.get("exclusions", {}) or {}).get("title_terms", []) or []
    enabled_regions = resolve_enabled_regions(config, region)
    source_preflight = probe_job_sources(title_filters, enabled_regions, config)
    source_skip_logged: set[str] = set()

    results: list[JobPosting] = []
    seen_urls: set[str] = set()
    cached_candidate_urls = load_cached_candidate_urls()
    candidate_cache_updates: set[str] = set()
    lock = threading.Lock()
    add_job = make_job_filter(
        config,
        seen_urls,
        results,
        title_filters,
        lock,
        cached_candidate_urls,
        candidate_cache_updates,
    )

    if not title_filters:
        logger.warning("[scraper] job_titles is empty; no source searches run")
        return []
    if not enabled_regions:
        logger.warning("[scraper] No enabled regions found in config/job_hunter.yml")
        return []

    if depth == "fast":
        logger.info("[scraper] depth=fast: skipping ATS search discovery")
        stats.record("ats_search_discovery", skipped=1)
    else:
        collect_ats_discovery(
            title_filters,
            enabled_regions,
            excluded_title_terms,
            run_disabled,
            stats,
            add_job,
        )

    collect_board_sources(
        title_filters,
        enabled_regions,
        config,
        stats,
        add_job,
        source_preflight,
        source_skip_logged,
    )

    llm_search_cfg = (config.get("search", {}) or {}).get("llm_search", {}) or {}
    llm_search_enabled = llm_search_cfg.get("enabled", False)
    if depth == "fast":
        logger.info("[scraper] depth=fast: skipping AI web search")
        stats.record("ai_web_search", skipped=1)
    elif llm_search_enabled:
        ai_min_jobs = int(llm_search_cfg.get("trigger_threshold", 0) or 0)
        below_threshold = ai_min_jobs <= 0 or len(results) < ai_min_jobs
        if depth != "deep" and not below_threshold:
            logger.info(
                "[scraper] Skipping AI web search: %s result(s) already meet threshold %s",
                len(results),
                ai_min_jobs,
            )
            stats.record("ai_web_search", skipped=1)
        else:
            collect_ai_web_search(title_filters, enabled_regions, stats, add_job)
    else:
        stats.record("ai_web_search", attempted=1)
        stats.record("ai_web_search", skipped=1)

    stats.log_summary(ats_only=all_providers_exhausted())
    logger.info("[scraper] Complete: %s jobs found", len(results))
    if candidate_cache_updates:
        save_cached_candidate_urls(cached_candidate_urls | candidate_cache_updates)
        logger.info("[scraper] Cached %s new discovery candidate URL(s)", len(candidate_cache_updates))
    return results
