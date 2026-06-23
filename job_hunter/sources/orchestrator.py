"""Job discovery orchestrator — canonical entry point for scraping.

Replaces sources/scraper/_boards.py with a correct per-region SearchParams dispatch.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from job_hunter.models import JobPosting, SearchParams

logger = logging.getLogger(__name__)


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


def scrape(region: str | None = None, *, depth: str = "standard") -> list[JobPosting]:
    """Scrape all enabled sources for the given region and return URL-deduped JobPostings."""
    from job_hunter.sources.boards import BOARD_REGISTRY
    from job_hunter.sources.scraper._config import enabled_regions as resolve_regions
    from job_hunter.sources.scraper._config import load_search_config
    from job_hunter.sources.search_providers.preflight import probe_search_providers
    from job_hunter.sources.search_providers.router import set_run_disabled

    cfg = load_search_config()
    job_titles: list[str] = cfg.get("job_titles", []) or []
    excluded_title_terms: list[str] = (cfg.get("exclusions", {}) or {}).get("title_terms", []) or []
    regions = resolve_regions(cfg, region)

    if not job_titles:
        logger.warning("[orchestrator] job_titles is empty; no sources will run")
        return []
    if not regions:
        logger.warning("[orchestrator] No enabled regions found in config/job_hunter.yml")
        return []

    start = time.monotonic()
    run_disabled = probe_search_providers()
    set_run_disabled(run_disabled)

    seen_urls: set[str] = set()
    results: list[JobPosting] = []

    def _add_unique(postings: list[JobPosting]) -> None:
        for jp in postings:
            url = jp.url or ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            results.append(jp)

    # Step 1: per-region board dispatch in parallel
    adapters = [cls() for cls in BOARD_REGISTRY.values()]
    for region_key, region_cfg in regions.items():
        params = _params_for_region(region_key, region_cfg, job_titles, excluded_title_terms)
        with ThreadPoolExecutor(max_workers=min(len(adapters), 8)) as pool:
            futures = {pool.submit(a.fetch, params): a.source_name for a in adapters}
            for future in as_completed(futures):
                try:
                    _add_unique(future.result())
                except Exception as exc:
                    logger.warning("[orchestrator] %s raised: %s", futures[future], exc)

    # Step 2: ATS discovery (once per run, not per region)
    if depth != "fast":
        try:
            from job_hunter.sources.search_providers.ats_discovery import discover_ats_jobs_by_search

            ats_raw = discover_ats_jobs_by_search(job_titles, regions, excluded_title_terms, disabled=run_disabled)
            _add_unique([JobPosting.from_dict(j) for j in ats_raw])
        except Exception as exc:
            logger.warning("[orchestrator] ATS discovery failed: %s", exc)

    # Step 3: LLM web search (optional)
    llm_cfg = (cfg.get("search", {}) or {}).get("llm_search", {}) or {}
    if depth != "fast" and llm_cfg.get("enabled"):
        threshold = int(llm_cfg.get("trigger_threshold", 0) or 0)
        if len(results) < threshold or depth == "deep":
            try:
                from job_hunter.sources.ai_web_search import fetch_ai_web_search_jobs

                ai_raw = fetch_ai_web_search_jobs(job_titles, regions)
                _add_unique([JobPosting.from_dict(j) for j in ai_raw])
            except Exception as exc:
                logger.warning("[orchestrator] LLM search failed: %s", exc)

    logger.info("[orchestrator] complete: %d jobs in %.1fs", len(results), time.monotonic() - start)
    return results
