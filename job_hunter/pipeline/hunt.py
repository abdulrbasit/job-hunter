"""Hunt pipeline — full autonomous chain (llm-api mode) or scrape+DB write (agent mode).

Stage order (llm-api): resolve region → scrape → dedup → enrich → validate → score → tailor → cover → pdf → readme → track
Stage order (agent):   resolve region → scrape → dedup → enrich → write to DB → exit
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_hunter.config.loader import ROOT as REPO_ROOT
from job_hunter.constants import DEFAULT_BATCH_SIZE
from job_hunter.core.url_liveness import UrlLivenessCache
from job_hunter.models import HuntInput, HuntOutput, JobPosting, ScrapeStats
from job_hunter.pipeline.enrichment import drop_dead_urls_before_enrichment, enrich_snippets
from job_hunter.pipeline.quality_gate import apply_pre_enrichment_quality_gate
from job_hunter.pipeline.stages.screening import screen_jobs_by_rules
from job_hunter.sources.jd_fetcher import fetch_jd
from job_hunter.sources.orchestrator import scrape_with_stats
from job_hunter.sources.search import canonicalize_url
from job_hunter.sources.source_config import enabled_regions, load_search_config
from job_hunter.tracking.discovery_cache import load_cached_candidate_urls, save_cached_candidate_urls
from job_hunter.tracking.processed_urls import filter_new_jobs
from job_hunter.tracking.repository import get_processed_urls, insert_jobs

logger = logging.getLogger(__name__)

type JobData = dict[str, Any]

# Each entry: (pass_name, scrape_with_stats kwargs). "standard"/"deep_boards" vary
# max_results (existing depth mechanism); "ats_slug"/"ats_discovery" isolate the
# two ATS stages that scrape_with_stats already knows how to run independently.
# Career-page/company discovery (a hypothetical pass 5) needs browser rendering,
# which is reserved for the separate company-hunt workflow — not run inline here.
_ADAPTIVE_PASSES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("standard", {"depth": "fast", "include_ats_slug": False, "include_ats_discovery": False}),
    ("deep_boards", {"depth": "deep", "include_ats_slug": False, "include_ats_discovery": False}),
    ("ats_slug", {"depth": "standard", "include_boards": False, "include_ats_discovery": False}),
    ("ats_discovery", {"depth": "standard", "include_boards": False, "include_ats_slug": False}),
)


def _drop_dead_urls(
    jobs: list[JobData],
    api_config: dict[str, Any],
    url_checker: Any = None,
) -> list[JobData]:
    return drop_dead_urls_before_enrichment(
        jobs,
        api_config,
        url_checker=url_checker or UrlLivenessCache().is_alive,
    )


def _enrich(jobs: list[JobData], api_config: dict[str, Any] | None = None) -> list[JobData]:
    return enrich_snippets(jobs, api_config, fetcher=fetch_jd)


def _drop_closed_postings(jobs: list[JobData]) -> list[JobData]:
    closed = [j for j in jobs if j.get("job_description_fetch_status") == "position_closed"]
    if closed:
        logger.info("[pipeline] Dropping %s closed/inactive posting(s) before scoring", len(closed))
        for j in closed:
            logger.info("  closed: %s @ %s", j.get("title", "?")[:50], j.get("company", "?"))
    return [j for j in jobs if j.get("job_description_fetch_status") != "position_closed"]


def _quality_target(scoring_config: dict[str, Any]) -> int:
    """Code-owned target resolver — scoring.batch_size if set, else DEFAULT_BATCH_SIZE.
    Not a new config field: batch_size already exists for scoring/tailoring batches."""
    batch_size = (scoring_config or {}).get("scoring", {}).get("batch_size")
    if isinstance(batch_size, int) and batch_size > 0:
        return batch_size
    return DEFAULT_BATCH_SIZE


def _dropped_by_source(before: list[JobData], after: list[JobData]) -> dict[str, int]:
    """Counts of `before` items missing from `after`, grouped by job source."""
    after_urls = {j.get("url") for j in after}
    counts: dict[str, int] = {}
    for job in before:
        if job.get("url") not in after_urls:
            src = str(job.get("source") or "unknown")
            counts[src] = counts.get(src, 0) + 1
    return counts


def _merge_counts(target: dict[str, int], increment: dict[str, int]) -> None:
    for key, value in increment.items():
        target[key] = target.get(key, 0) + value


class _PassSummary:
    """Per-pass candidate counts for the region observability log line."""

    __slots__ = ("after_dead_url", "after_quality_gate", "closed", "final")

    def __init__(self) -> None:
        self.after_dead_url = 0
        self.after_quality_gate = 0
        self.closed = 0
        self.final = 0


def _new_candidate_dicts(postings: Iterable[JobPosting], seen_canonical: set[str]) -> list[JobData]:
    """Convert source models once while dropping URLs already seen in this region."""
    candidates: list[JobData] = []
    for posting in postings:
        job = posting.model_dump()
        canonical = canonicalize_url(job.get("url", ""))
        if canonical and canonical not in seen_canonical:
            seen_canonical.add(canonical)
            candidates.append(job)
    return candidates


def _process_candidates(
    jobs: list[JobData],
    api_config: dict[str, Any],
    scoring_config: dict[str, Any],
    url_liveness: UrlLivenessCache,
    stats: ScrapeStats,
) -> tuple[list[JobData], _PassSummary]:
    """Run one batch of raw candidates through the same policy/quality pipeline as
    a standard hunt: dead-url check, pre-enrichment quality gate, enrichment,
    closed-posting drop, objective screen. Used between every adaptive pass so
    quality filtering is never skipped or weakened. Dead/closed drops are
    recorded on `stats`, grouped by source, for the region summary log."""
    summary = _PassSummary()
    if not jobs:
        return [], summary

    alive = _drop_dead_urls(jobs, api_config, url_liveness.is_alive)
    _merge_counts(stats.dead_by_source, _dropped_by_source(jobs, alive))
    summary.after_dead_url = len(alive)
    if not alive:
        return [], summary

    gated, _rejected = apply_pre_enrichment_quality_gate(alive, scoring_config)
    summary.after_quality_gate = len(gated)

    enriched = _enrich(gated, api_config)
    not_closed = _drop_closed_postings(enriched)
    _merge_counts(stats.closed_by_source, _dropped_by_source(enriched, not_closed))
    summary.closed = len(enriched) - len(not_closed)

    screened, _rejected = screen_jobs_by_rules(not_closed, scoring_config)
    summary.final = len(screened)
    return screened, summary


def _merge_region_stats(stats: ScrapeStats, pass_stats: ScrapeStats) -> None:
    """Fold one pass's scrape_with_stats output into the run-level accumulator."""
    _merge_counts(stats.fetched_by_region, pass_stats.fetched_by_region)
    _merge_counts(stats.accepted_by_region, pass_stats.accepted_by_region)
    for region_key, reasons in pass_stats.rejected_by_region_reason.items():
        target_reasons = stats.rejected_by_region_reason.setdefault(region_key, {})
        _merge_counts(target_reasons, reasons)
    for region_key, sources in pass_stats.accepted_by_region_source.items():
        target_sources = stats.accepted_by_region_source.setdefault(region_key, {})
        _merge_counts(target_sources, sources)


def _adaptive_region_hunt(
    region_key: str,
    api_config: dict[str, Any],
    scoring_config: dict[str, Any],
    url_liveness: UrlLivenessCache,
    target: int,
    stats: ScrapeStats,
    force: bool = False,
) -> list[JobData]:
    """Escalate through scraping passes for one region until `target` quality
    candidates are found, or every pass has run. Each pass's new candidates get
    the full policy/quality pipeline before counting toward the target, and the
    per-region canonical-URL set prevents a later pass from re-processing a job
    an earlier pass already picked up. Per-pass and per-region totals accumulate
    onto `stats` for the final observability summary line."""
    quality_jobs: list[JobData] = []
    seen_canonical: set[str] = set()
    ran_passes: list[str] = []
    fetched_total = 0
    deduped_total = 0
    after_policy_total = 0
    after_quality_gate_total = 0
    dead_url_total = 0
    closed_total = 0

    for pass_name, scrape_kwargs in _ADAPTIVE_PASSES:
        postings, pass_stats = scrape_with_stats(region=region_key, **scrape_kwargs)
        fetched_total += pass_stats.total_fetched
        after_policy_total += pass_stats.total_after_policy
        _merge_region_stats(stats, pass_stats)

        candidates = _new_candidate_dicts(postings, seen_canonical)
        new_jobs, _existing = filter_new_jobs(candidates, force=force)
        deduped_total += len(new_jobs)

        pass_quality, summary = _process_candidates(new_jobs, api_config, scoring_config, url_liveness, stats)
        dead_url_total += len(new_jobs) - summary.after_dead_url
        after_quality_gate_total += summary.after_quality_gate
        closed_total += summary.closed
        quality_jobs.extend(pass_quality)
        ran_passes.append(pass_name)
        met = len(quality_jobs) >= target
        logger.info(
            "region=%s pass=%s quality=%d target=%d%s",
            region_key,
            pass_name,
            len(quality_jobs),
            target,
            " status=met" if met else "",
        )
        if met:
            break

    if len(quality_jobs) < target:
        stats.under_target_regions.append(region_key)
        logger.info("region=%s status=under_target exhausted_passes=%s", region_key, ran_passes)

    logger.info(
        "region=%s fetched=%d deduped=%d after_policy=%d after_quality_gate=%d "
        "dead_url=%d closed=%d final_candidates=%d target_met=%s",
        region_key,
        fetched_total,
        deduped_total,
        after_policy_total,
        after_quality_gate_total,
        dead_url_total,
        closed_total,
        len(quality_jobs),
        str(len(quality_jobs) >= target).lower(),
    )
    return quality_jobs


def _adaptive_hunt(
    regions: dict[str, dict[str, Any]],
    api_config: dict[str, Any],
    scoring_config: dict[str, Any],
    url_liveness: UrlLivenessCache,
    force: bool = False,
) -> tuple[list[JobData], ScrapeStats]:
    """Escalate every region in `regions` through _adaptive_region_hunt, returning
    deduped quality candidates ready for DB insert/scoring plus accumulated stats.

    Shared by run_hunt (llm-api) and run_hunt_scrape_only (agent/scrape-only) so
    both modes get the same per-region escalation: each region (e.g. Bahrain)
    gets its own full pass budget instead of being diluted inside one global
    scrape+filter run dominated by larger regions (e.g. Germany).

    `force` allows previously-processed URLs to re-enter this run (--force) while
    same-run canonical-URL dedup (seen_canonical, both here and per-region) still applies.
    """
    target = _quality_target(scoring_config)
    logger.info("[pipeline] Adaptive hunt: %d region(s), target=%d quality jobs each", len(regions), target)

    stats = ScrapeStats()
    all_jobs: list[JobData] = []
    seen_canonical: set[str] = set()
    for region_key in regions:
        for job in _adaptive_region_hunt(
            region_key, api_config, scoring_config, url_liveness, target, stats, force=force
        ):
            canonical = canonicalize_url(job.get("url", ""))
            if not canonical or canonical not in seen_canonical:
                if canonical:
                    seen_canonical.add(canonical)
                all_jobs.append(job)

    if stats.under_target_regions:
        logger.info(
            "[pipeline] %d/%d region(s) under target: %s",
            len(stats.under_target_regions),
            len(regions),
            stats.under_target_regions,
        )
    return all_jobs, stats


def run_hunt(
    args: dict,
    api_config: dict[str, Any],
    scoring_config: dict[str, Any],
    url_liveness: UrlLivenessCache,
) -> tuple[list[JobData], set[str], set[str]]:
    """Execute the hunt mode: adaptive per-region scrape, URL-check, enrich.

    `args["depth"]` (from --depth) is accepted for CLI/API compatibility but unused here:
    adaptive mode always escalates through its own fixed pass depths (see _ADAPTIVE_PASSES).
    """
    config = load_search_config()
    regions = enabled_regions(config, args.get("region"))
    if not regions:
        logger.warning("[pipeline] No enabled regions found in config/job_hunter.yml")
        return [], set(), set()

    all_jobs, _stats = _adaptive_hunt(regions, api_config, scoring_config, url_liveness, force=bool(args.get("force")))
    if not all_jobs:
        logger.warning("[pipeline] No new jobs found. Exiting.")
        return [], set(), set()

    return all_jobs, set(), set()


def run_hunt_scrape_only(
    region: str | None = None,
    root: str | Path = REPO_ROOT,
    api_config: dict[str, Any] | None = None,
    url_checker: Any = None,
    depth: str = "standard",
    force: bool = False,
) -> tuple[str, int, ScrapeStats]:
    """Adaptive per-region scrape (same escalation as run_hunt), URL-check,
    enrichment, screening, then write jobs to DB.

    `depth` is accepted for CLI/API compatibility but unused: adaptive mode
    always escalates through its own fixed pass depths (see run_hunt).
    `force` (--force) lets previously-processed URLs re-enter this run.

    Returns (run_id, candidate_count, stats).
    """
    from job_hunter.config import get_config

    root = Path(root)
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    scoring_config = get_config("job_hunter")

    config = load_search_config()
    regions = enabled_regions(config, region)
    if not regions:
        logger.warning("[pipeline] No enabled regions found in config/job_hunter.yml")
        jobs: list[JobData] = []
        stats = ScrapeStats()
    else:
        url_liveness = UrlLivenessCache(checker=url_checker)
        jobs, stats = _adaptive_hunt(regions, api_config or {}, scoring_config, url_liveness, force=force)
    stats.total_after_policy = len(jobs)

    # Write to DB (replaces snapshot JSON)
    if jobs:
        inserted = insert_jobs(root, jobs, run_id=run_id)
        logger.info("[pipeline] Wrote %s job(s) to DB (run_id=%s)", inserted, run_id)

    # Update discovery cache
    cached = load_cached_candidate_urls()
    cached.update(canonicalize_url(job.get("url", "")) for job in jobs if job.get("url"))
    save_cached_candidate_urls(cached)

    logger.info("[pipeline] Hunt complete: run_id=%s candidates=%s", run_id, len(jobs))
    return run_id, len(jobs), stats


def load_hunt_snapshot(path: str | Path) -> tuple[list[JobData], set[str], set[str]]:
    """Load a scrape handoff snapshot for downstream hunt processing (llm-api mode)."""
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    jobs = data.get("jobs") or []
    existing_urls = set(data.get("existing_urls") or []) or get_processed_urls(Path(path).parent.parent.parent)
    existing_titles = set(data.get("existing_titles") or [])
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
        run_id, count, stats = run_hunt_scrape_only(region, depth=inp.depth, force=inp.force)
        return HuntOutput(
            run_id=run_id,
            stats=stats,
            mode=inp.mode,
        )

    # llm-api mode: delegate to the pipeline runner for full pipeline
    from job_hunter.pipeline.context import PipelineCommandOptions
    from job_hunter.pipeline.runner import run as orch_run

    options = PipelineCommandOptions(
        mode="hunt",
        region=region,
        depth=inp.depth,
        scrape_only=inp.scrape_only,
        from_snapshot=str(inp.from_snapshot) if inp.from_snapshot else None,
        from_db_candidates=inp.from_db_candidates,
        skip_score=inp.skip_score,
        skip_validate=inp.skip_validate,
        force=inp.force,
    )
    orch_run(options)
    return HuntOutput(stats=ScrapeStats(), mode=inp.mode)
