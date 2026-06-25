"""Hunt pipeline — full autonomous chain (llm-api mode) or scrape+snapshot (agent mode).

Stage order (llm-api): resolve region → scrape → dedup → enrich → validate → score → tailor → cover → pdf → readme → track
Stage order (agent):   resolve region → scrape → dedup → enrich → snapshot → exit

CLI routes here via pipeline/orchestrator.py based on config mode.
Original hunt_pipeline.py logic preserved below; mode dispatch added above it.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from job_hunter.config.loader import ROOT as REPO_ROOT
from job_hunter.core.url_liveness import UrlLivenessCache
from job_hunter.models import HuntInput, HuntOutput, ScrapeStats
from job_hunter.pipeline.enrichment import drop_dead_urls_before_enrichment, enrich_snippets
from job_hunter.pipeline.screening import hard_screen_jobs
from job_hunter.sources.jd_fetcher import fetch_jd
from job_hunter.sources.orchestrator import scrape_with_stats
from job_hunter.sources.search_providers import canonicalize_url
from job_hunter.tracking.discovery_cache import load_cached_candidate_urls, save_cached_candidate_urls
from job_hunter.tracking.tracker import filter_new_jobs, load_processed

logger = logging.getLogger(__name__)


def _jobs_from_hunt(
    region: str | None = None, depth: str = "standard"
) -> tuple[list[dict[str, Any]], set[str], set[str], ScrapeStats]:
    """Scrape all enabled sources, then deduplicate against processed jobs."""
    postings, stats = scrape_with_stats(region=region, depth=depth)
    jobs = [posting.to_dict() for posting in postings]
    if not jobs:
        return [], set(), set(), stats
    new_jobs, existing_urls = filter_new_jobs(jobs)
    seen_canonical: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for job in new_jobs:
        c = canonicalize_url(job.get("url", ""))
        if not c or c not in seen_canonical:
            if c:
                seen_canonical.add(c)
            deduped.append(job)
    dropped = len(new_jobs) - len(deduped)
    if dropped:
        logger.info("[pipeline] Dropped %s canonical-URL duplicate(s) before enrichment", dropped)
    return deduped, existing_urls, set(), stats


def _drop_dead_urls(
    jobs: list[dict[str, Any]],
    api_cfg: dict[str, Any],
    url_checker: Any = None,
) -> list[dict[str, Any]]:
    return drop_dead_urls_before_enrichment(
        jobs,
        api_cfg,
        url_checker=url_checker or UrlLivenessCache().is_alive,
    )


def _enrich(jobs: list[dict[str, Any]], api_cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return enrich_snippets(jobs, api_cfg, fetcher=fetch_jd)


def _drop_closed_postings(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    closed = [j for j in jobs if j.get("fetch_status") == "position_closed"]
    if closed:
        logger.info("[pipeline] Dropping %s closed/inactive posting(s) before scoring", len(closed))
        for j in closed:
            logger.info("  closed: %s @ %s", j.get("title", "?")[:50], j.get("company", "?"))
    return [j for j in jobs if j.get("fetch_status") != "position_closed"]


def run_hunt(
    args: dict,
    api_cfg: dict[str, Any],
    scoring_cfg: dict[str, Any],
    url_liveness: UrlLivenessCache,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """
    Execute the hunt mode: scrape, URL-check, enrich.

    Returns (jobs, existing_urls, existing_titles) ready for downstream processing,
    or ([], set(), set()) when there is nothing to process.
    """
    logger.info("[pipeline] Step 1: Scraping and deduplicating jobs...")
    jobs, existing_urls, existing_titles, _stats = _jobs_from_hunt(args["region"], depth=args.get("depth", "standard"))
    if not jobs:
        logger.warning("[pipeline] No new jobs found. Exiting.")
        return [], set(), set()

    jobs = _drop_dead_urls(jobs, api_cfg, url_liveness.is_alive)
    if not jobs:
        logger.warning("[pipeline] All scraped jobs failed URL verification before enrichment.")
        return [], set(), set()

    logger.info("[pipeline] Step 1b: Enriching sparse job descriptions...")
    jobs = _enrich(jobs, api_cfg)
    jobs = _drop_closed_postings(jobs)
    jobs, rejected = hard_screen_jobs(jobs, scoring_cfg)
    if rejected:
        logger.info("[pipeline] Objective screen rejected %s job(s)", len(rejected))
    return jobs, existing_urls, existing_titles


def _snapshot_path(root: str | Path, date: str, region: str | None) -> Path:
    candidates_dir = Path(root) / "outputs" / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    return candidates_dir / f"{timestamp}_{region or 'all'}_candidates.json"


def run_hunt_scrape_only(
    region: str | None = None,
    root: str | Path = REPO_ROOT,
    api_cfg: dict[str, Any] | None = None,
    url_checker: Any = None,
    depth: str = "standard",
) -> tuple[Path, int, ScrapeStats]:
    """Run scrape, dedup, URL check, and enrichment, then write a handoff snapshot."""
    now = datetime.now(UTC)
    today = now.date().isoformat()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    jobs, existing_urls, existing_titles, stats = _jobs_from_hunt(region, depth=depth)

    if jobs:
        jobs = _drop_dead_urls(jobs, api_cfg or {}, url_checker)
    if jobs:
        jobs = _enrich(jobs, api_cfg or {})
        jobs = _drop_closed_postings(jobs)
    if jobs:
        from job_hunter.config import get_config

        jobs, rejected = hard_screen_jobs(jobs, get_config("job_hunter"))
        if rejected:
            logger.info("[pipeline] Objective screen rejected %s job(s)", len(rejected))
    stats.total_after_policy = len(jobs)

    payload = {
        "date": today,
        "created_at": now.isoformat(),
        "run_id": run_id,
        "package_version": _package_version(),
        "region": region or "all",
        "count": len(jobs),
        "jobs": jobs,
        "stats": stats.model_dump(),
        "existing_urls": sorted(existing_urls),
        "existing_titles": sorted(existing_titles),
    }
    path = _snapshot_path(root, today, region)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    cached = load_cached_candidate_urls()
    cached.update(canonicalize_url(job.get("url", "")) for job in jobs if job.get("url"))
    save_cached_candidate_urls(cached)
    logger.info("[pipeline] Scrape snapshot written: %s", path)
    return path, len(jobs), stats


def _package_version() -> str:
    try:
        return version("job-hunter-kit")
    except PackageNotFoundError:
        return "development"


def load_hunt_snapshot(path: str | Path) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Load a scrape handoff snapshot for downstream hunt processing."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    jobs = data.get("jobs") or []
    existing_urls_raw = data.get("existing_urls")
    existing_titles_raw = data.get("existing_titles")
    if existing_urls_raw is None:
        existing_urls = load_processed()
        existing_titles = set()
    else:
        existing_urls = set(existing_urls_raw or [])
        existing_titles = set(existing_titles_raw or [])
    return jobs, existing_urls, existing_titles


def run(inp: HuntInput) -> HuntOutput:
    """Unified hunt entry point for dispatch_hunt. Mode-aware."""
    region: str | None = inp.region_key if inp.region_key != "all" else None

    if inp.mode == "agent" or inp.scrape_only:
        if inp.from_snapshot:
            jobs, _, _ = load_hunt_snapshot(inp.from_snapshot)
            return HuntOutput(
                snapshot_path=inp.from_snapshot,
                stats=ScrapeStats(total_fetched=len(jobs)),
                mode=inp.mode,
            )
        path, count, stats = run_hunt_scrape_only(region, depth=inp.depth)
        return HuntOutput(
            snapshot_path=path,
            stats=stats,
            mode=inp.mode,
        )

    # llm-api mode: delegate to orchestrator for full pipeline
    from job_hunter.pipeline.orchestrator import run as orch_run

    ns = {
        "mode": "hunt",
        "region": region,
        "depth": inp.depth,
        "scrape_only": inp.scrape_only,
        "from_snapshot": str(inp.from_snapshot) if inp.from_snapshot else None,
        "skip_score": inp.skip_score,
        "skip_validate": inp.skip_validate,
        "force": inp.force,
        "links": None,
        "jd": None,
        "title": None,
        "company": None,
    }
    orch_run(ns)
    return HuntOutput(stats=ScrapeStats(), mode=inp.mode)
