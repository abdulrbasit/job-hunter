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
from job_hunter.config.reference_data import resolve_title_exclusions
from job_hunter.constants import DEFAULT_BACKFILL_MAX_RESULTS, DEFAULT_STANDARD_MAX_RESULTS
from job_hunter.models import JobPosting, ScrapeStats, SearchParams
from job_hunter.sources.ats_slugs import (
    catalog_slugs,
    harvest_slugs,
    load_slug_store,
    query_ats_by_slugs,
    update_slug_store,
)
from job_hunter.sources.policy import JobPolicy, derive_country_code, normalize_employment_type
from job_hunter.sources.search import canonicalize_url
from job_hunter.sources.search.preflight import probe_search_providers
from job_hunter.sources.search.router import set_run_disabled
from job_hunter.sources.source_config import enabled_regions as resolve_regions
from job_hunter.sources.source_config import load_search_config
from job_hunter.tracking.discovery_cache import load_cached_candidate_urls

logger = logging.getLogger(__name__)


def board_adapters() -> list[Any]:
    from job_hunter.sources.boards import BOARD_REGISTRY

    return [cls() for cls in BOARD_REGISTRY.values()]


def _max_results_for_depth(depth: str) -> int:
    """Larger max_results is an adaptive/deep-attempt signal only — standard runs
    keep the existing per-source target so paged adapters don't change behavior."""
    return DEFAULT_BACKFILL_MAX_RESULTS if depth == "deep" else DEFAULT_STANDARD_MAX_RESULTS


def _params_for_region(
    region_key: str,
    region_config: dict[str, Any],
    job_titles: list[str],
    excluded_title_terms: list[str],
    *,
    max_results: int = DEFAULT_STANDARD_MAX_RESULTS,
) -> SearchParams:
    return SearchParams(
        region_key=region_key,
        country=region_config.get("country", ""),
        location=region_config.get("location", ""),
        search_lang=region_config.get("search_lang", "en"),
        job_titles=job_titles,
        max_results=max_results,
        excluded_title_terms=excluded_title_terms,
    )


def scrape_with_stats(
    region: str | None = None,
    *,
    depth: str = "standard",
    include_boards: bool = True,
    include_ats_slug: bool = True,
    include_ats_discovery: bool = True,
) -> tuple[list[JobPosting], ScrapeStats]:
    """The include_* flags default to True (preserving prior behavior for every
    existing caller) and exist so adaptive per-region passes (pipeline/hunt.py)
    can request one stage at a time — boards-only, ATS-slug-only, or
    ATS-discovery-only — without duplicating this function's policy filtering."""
    config = load_search_config()
    job_titles: list[str] = config.get("job_titles", []) or []
    excluded_title_terms: list[str] = resolve_title_exclusions(config)
    regions = resolve_regions(config, region)
    max_results = _max_results_for_depth(depth)

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
    policy = JobPolicy(config)
    results: list[JobPosting] = []
    rejected: Counter[str] = Counter()

    def _add_unique(
        postings: list[JobPosting],
        source: str,
        *,
        search_lang: str = "en",
        region_config: dict[str, Any] | None = None,
    ) -> None:
        source_rejected: Counter[str] = Counter()

        def reject(reason: str, region_key: str) -> None:
            rejected[reason] += 1
            source_rejected[reason] += 1
            region_reasons = stats.rejected_by_region_reason.setdefault(region_key, {})
            region_reasons[reason] = region_reasons.get(reason, 0) + 1

        stats.total_fetched += len(postings)
        stats.by_source[source] = stats.by_source.get(source, 0) + len(postings)
        for jp in postings:
            region_key = jp.region or "unknown"
            stats.fetched_by_region[region_key] = stats.fetched_by_region.get(region_key, 0) + 1
            url = canonicalize_url(jp.url or "")
            if not url:
                reject("missing_url", region_key)
                continue
            if url in cached_urls:
                reject("cached_candidate", region_key)
                continue
            if url in seen_urls:
                reject("duplicate_url", region_key)
                continue
            stats.total_after_dedup += 1
            if policy.is_excluded_url(jp.url) or not policy.is_valid_job_url(jp.url):
                reject("invalid_url", region_key)
                continue
            reason = policy.rejection_reason(jp.model_dump(), job_titles)
            if reason:
                reject(reason, region_key)
                continue
            if policy.excluded_by_search_lang(jp.title or "", jp.snippet or "", search_lang):
                reject("excluded_by_search_lang", region_key)
                continue
            effective_region_config = region_config or regions.get(jp.region, {})
            if policy.has_incompatible_location_metadata(jp.model_dump(), effective_region_config):
                reject("incompatible_location_metadata", region_key)
                continue
            if policy.has_wrong_location(jp.model_dump(), effective_region_config):
                reject("wrong_location", region_key)
                continue
            if not effective_region_config and policy.has_incompatible_location_for_global_feed(jp.model_dump()):
                reject("incompatible_location_metadata", region_key)
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
            stats.accepted_by_region[region_key] = stats.accepted_by_region.get(region_key, 0) + 1
            region_sources = stats.accepted_by_region_source.setdefault(region_key, {})
            region_sources[source] = region_sources.get(source, 0) + 1
        if source_rejected:
            stats.rejected_by_source[source] = dict(source_rejected)

    adapters = board_adapters() if include_boards else []
    global_adapters = [adapter for adapter in adapters if getattr(adapter, "global_feed", False)]
    regional_adapters = [adapter for adapter in adapters if not getattr(adapter, "global_feed", False)]

    if global_adapters and region is None:
        global_params = SearchParams(
            region_key="global_remote",
            country="",
            location="",
            search_lang="en",
            job_titles=job_titles,
            max_results=max_results,
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
        for region_key, region_config in regions.items():
            params = _params_for_region(
                region_key, region_config, job_titles, excluded_title_terms, max_results=max_results
            )
            with ThreadPoolExecutor(max_workers=min(len(global_adapters), 4)) as pool:
                futures = {pool.submit(adapter.fetch, params): adapter.source_name for adapter in global_adapters}
                for future in as_completed(futures):
                    source = futures[future]
                    try:
                        _add_unique(
                            future.result(), source, search_lang=params.search_lang, region_config=region_config
                        )
                    except Exception as exc:
                        stats.failed_sources.append(source)
                        logger.warning("[orchestrator] %s raised: %s", source, exc)

    # Step 1: per-region board dispatch in parallel
    if regional_adapters:
        for region_key, region_config in regions.items():
            params = _params_for_region(
                region_key, region_config, job_titles, excluded_title_terms, max_results=max_results
            )
            with ThreadPoolExecutor(max_workers=min(len(regional_adapters), 8)) as pool:
                futures = {pool.submit(a.fetch, params): a.source_name for a in regional_adapters}
                for future in as_completed(futures):
                    source = futures[future]
                    try:
                        _add_unique(
                            future.result(), source, search_lang=params.search_lang, region_config=region_config
                        )
                    except Exception as exc:
                        stats.failed_sources.append(source)
                        logger.warning("[orchestrator] %s raised: %s", source, exc)

    # Step 2: Harvest slugs from board results, persist, query ATS APIs directly (no keys needed).
    # Catalog slugs are unioned in at query time only — never persisted — so region and
    # industry filters apply fresh each run.
    if include_ats_slug and depth != "fast":
        try:
            new_slugs = harvest_slugs(results)
            update_slug_store(_WORKSPACE_ROOT, new_slugs)
            slug_store = load_slug_store(_WORKSPACE_ROOT)
            for platform, slugs in catalog_slugs(config).items():
                slug_store[platform] = sorted(set(slug_store.get(platform, [])) | slugs)
            slug_jobs = query_ats_by_slugs(slug_store, job_titles, regions, excluded_title_terms)
            _add_unique([JobPosting.model_validate(j) for j in slug_jobs], "ats_slug")
        except Exception as exc:
            logger.warning("[orchestrator] ATS slug cache query failed: %s", exc)

    # Step 3: ATS discovery via search (once per run, discovers new companies)
    if include_ats_discovery and depth != "fast":
        try:
            from job_hunter.sources.search.ats_discovery import discover_ats_jobs_by_search

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
