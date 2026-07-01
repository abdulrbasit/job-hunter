"""Job discovery orchestrator — canonical entry point for scraping.

Each JobSourceAdapter receives a proper SearchParams object (not raw config dicts).

Flow:
  1. Load config, resolve enabled regions
  2. Per region: fetch all board adapters in parallel via SearchParams
  3. ATS discovery (once per run, search-provider-backed)
  4. LLM web search (optional, gated by config threshold)
  5. URL-dedup, return list[JobPosting]
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from job_hunter.config.loader import ROOT as _WORKSPACE_ROOT
from job_hunter.models import JobPosting, ScrapeStats, SearchParams
from job_hunter.sources._policy import JobPolicy, derive_country_code, normalize_employment_type
from job_hunter.sources.ats_slugs import harvest_slugs, load_slug_store, query_ats_by_slugs, update_slug_store
from job_hunter.sources.search_providers import canonicalize_url
from job_hunter.sources.search_providers.preflight import probe_search_providers
from job_hunter.sources.search_providers.router import set_run_disabled
from job_hunter.sources.source_config import enabled_regions as resolve_regions
from job_hunter.sources.source_config import load_search_config
from job_hunter.tracking.discovery_cache import load_cached_candidate_urls

logger = logging.getLogger(__name__)


def board_adapters() -> list[Any]:
    from job_hunter.sources.boards import BOARD_REGISTRY

    return [cls() for cls in BOARD_REGISTRY.values()]


def _params_for_region(
    region_key: str,
    region_cfg: dict[str, Any],
    job_titles: list[str],
    excluded_title_terms: list[str],
) -> SearchParams:
    return SearchParams(
        region_key=region_key,
        country=region_cfg.get("country", ""),
        location=region_cfg.get("location", ""),
        search_lang=region_cfg.get("search_lang", "en"),
        job_titles=job_titles,
        excluded_title_terms=excluded_title_terms,
    )


def scrape_with_stats(region: str | None = None, *, depth: str = "standard") -> tuple[list[JobPosting], ScrapeStats]:
    cfg = load_search_config()
    job_titles: list[str] = cfg.get("job_titles", []) or []
    excluded_title_terms: list[str] = (cfg.get("exclusions", {}) or {}).get("title_terms", []) or []
    regions = resolve_regions(cfg, region)

    if not job_titles:
        logger.warning("[orchestrator] job_titles is empty; no sources will run")
        return [], ScrapeStats()
    if not regions:
        logger.warning("[orchestrator] No enabled regions found in config/job_hunter.yml")
        return [], ScrapeStats()

    start = time.monotonic()
    stats = ScrapeStats()
    run_disabled = probe_search_providers()
    set_run_disabled(run_disabled)

    seen_urls: set[str] = set()
    cached_urls = load_cached_candidate_urls()
    policy = JobPolicy(cfg)
    results: list[JobPosting] = []
    rejected: Counter[str] = Counter()

    def _add_unique(
        postings: list[JobPosting],
        source: str,
        *,
        search_lang: str = "en",
        region_cfg: dict[str, Any] | None = None,
    ) -> None:
        source_rejected: Counter[str] = Counter()

        def reject(reason: str) -> None:
            rejected[reason] += 1
            source_rejected[reason] += 1

        stats.total_fetched += len(postings)
        stats.by_source[source] = stats.by_source.get(source, 0) + len(postings)
        for jp in postings:
            url = canonicalize_url(jp.url or "")
            if not url:
                reject("missing_url")
                continue
            if url in cached_urls:
                reject("cached_candidate")
                continue
            if url in seen_urls:
                reject("duplicate_url")
                continue
            stats.total_after_dedup += 1
            if policy.is_excluded_url(jp.url) or not policy.is_valid_job_url(jp.url):
                reject("invalid_url")
                continue
            reason = policy.rejection_reason(jp.model_dump(), job_titles)
            if reason:
                reject(reason)
                continue
            if policy.excluded_by_search_lang(jp.title or "", jp.snippet or "", search_lang):
                reject("excluded_by_search_lang")
                continue
            effective_region_cfg = region_cfg or regions.get(jp.region, {})
            if policy.has_incompatible_location_metadata(jp.model_dump(), effective_region_cfg):
                reject("incompatible_location_metadata")
                continue
            if policy.has_wrong_location(jp.model_dump(), effective_region_cfg):
                reject("wrong_location")
                continue
            if not effective_region_cfg and policy.has_incompatible_location_for_global_feed(jp.model_dump()):
                reject("incompatible_location_metadata")
                continue
            seen_urls.add(url)
            results.append(
                jp.model_copy(
                    update={
                        "posting_date_status": policy.posting_date_status(jp.posted_date_text),
                        "employment_type": normalize_employment_type(jp.employment_type),
                        "country_code": derive_country_code(jp.location),
                    }
                )
            )
            stats.total_after_policy += 1
            stats.accepted_by_source[source] = stats.accepted_by_source.get(source, 0) + 1
        if source_rejected:
            stats.rejected_by_source[source] = dict(source_rejected)

    adapters = board_adapters()
    global_adapters = [adapter for adapter in adapters if getattr(adapter, "global_feed", False)]
    regional_adapters = [adapter for adapter in adapters if not getattr(adapter, "global_feed", False)]

    if global_adapters and region is None:
        global_params = SearchParams(
            region_key="global_remote",
            country="",
            location="",
            search_lang="en",
            job_titles=job_titles,
            excluded_title_terms=excluded_title_terms,
        )
        with ThreadPoolExecutor(max_workers=min(len(global_adapters), 4)) as pool:
            futures = {pool.submit(adapter.fetch, global_params): adapter.source_name for adapter in global_adapters}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    postings = [posting.model_copy(update={"region": "global_remote"}) for posting in future.result()]
                    _add_unique(postings, source)
                except Exception as exc:
                    stats.failed_sources.append(source)
                    logger.warning("[orchestrator] %s raised: %s", source, exc)
    elif global_adapters:
        for region_key, region_cfg in regions.items():
            params = _params_for_region(region_key, region_cfg, job_titles, excluded_title_terms)
            with ThreadPoolExecutor(max_workers=min(len(global_adapters), 4)) as pool:
                futures = {pool.submit(adapter.fetch, params): adapter.source_name for adapter in global_adapters}
                for future in as_completed(futures):
                    source = futures[future]
                    try:
                        _add_unique(future.result(), source, search_lang=params.search_lang, region_cfg=region_cfg)
                    except Exception as exc:
                        stats.failed_sources.append(source)
                        logger.warning("[orchestrator] %s raised: %s", source, exc)

    # Step 1: per-region board dispatch in parallel
    if regional_adapters:
        for region_key, region_cfg in regions.items():
            params = _params_for_region(region_key, region_cfg, job_titles, excluded_title_terms)
            with ThreadPoolExecutor(max_workers=min(len(regional_adapters), 8)) as pool:
                futures = {pool.submit(a.fetch, params): a.source_name for a in regional_adapters}
                for future in as_completed(futures):
                    source = futures[future]
                    try:
                        _add_unique(future.result(), source, search_lang=params.search_lang, region_cfg=region_cfg)
                    except Exception as exc:
                        stats.failed_sources.append(source)
                        logger.warning("[orchestrator] %s raised: %s", source, exc)

    # Step 2: Harvest slugs from board results, persist, query ATS APIs directly (no keys needed)
    if depth != "fast":
        try:
            new_slugs = harvest_slugs(results)
            update_slug_store(_WORKSPACE_ROOT, new_slugs)
            slug_store = load_slug_store(_WORKSPACE_ROOT)
            slug_jobs = query_ats_by_slugs(slug_store, job_titles, regions, excluded_title_terms)
            _add_unique([JobPosting.model_validate(j) for j in slug_jobs], "ats_slug")
        except Exception as exc:
            logger.warning("[orchestrator] ATS slug cache query failed: %s", exc)

    # Step 3: ATS discovery via search (once per run, discovers new companies)
    if depth != "fast":
        try:
            from job_hunter.sources.search_providers.ats_discovery import discover_ats_jobs_by_search

            ats_raw = discover_ats_jobs_by_search(job_titles, regions, excluded_title_terms, disabled=run_disabled)
            _add_unique([JobPosting.model_validate(j) for j in ats_raw], "ats_discovery")
        except Exception as exc:
            logger.warning("[orchestrator] ATS discovery failed: %s", exc)

    stats.rejected = dict(rejected)
    stats.duration_seconds = time.monotonic() - start
    logger.info(
        "[orchestrator] complete fetched=%d deduped=%d accepted=%d by_source=%s accepted_by_source=%s "
        "rejected=%s rejected_by_source=%s failed=%s duration=%.1fs",
        stats.total_fetched,
        stats.total_after_dedup,
        stats.total_after_policy,
        stats.by_source,
        stats.accepted_by_source,
        stats.rejected,
        stats.rejected_by_source,
        stats.failed_sources,
        stats.duration_seconds,
    )
    return results, stats


def scrape(region: str | None = None, *, depth: str = "standard") -> list[JobPosting]:
    results, _stats = scrape_with_stats(region, depth=depth)
    return results
