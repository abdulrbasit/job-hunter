"""
Job hunt pipeline orchestrator.

Two modes, one entry point:

  hunt (default)   Search all enabled job sources and boards for configured titles.
                   Runs daily via GitHub Actions.

  tailor-links     Tailor resume for a specific list of URLs.
                   Pass --links "URL1, URL2" or set TAILOR_LINKS env var.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Any

from job_hunter.config.loader import ROOT as REPO_ROOT
from job_hunter.config.loader import get_config, load_api_config, profile_path, setup_logging
from job_hunter.constants import DEFAULT_BATCH_SIZE
from job_hunter.core.url_liveness import UrlLivenessCache
from job_hunter.pipeline import _match_processor
from job_hunter.pipeline._artifacts import write_match_artifacts
from job_hunter.pipeline.cover_writer import write_cover
from job_hunter.pipeline.hunt import (
    load_hunt_snapshot,
    run_hunt,
    run_hunt_scrape_only,
)
from job_hunter.pipeline.pdf_compiler import compile_tex
from job_hunter.pipeline.pre_llm_gate import apply_pre_llm_gate
from job_hunter.pipeline.readme_writer import slugify
from job_hunter.pipeline.readme_writer import update_readme as write_readme_table
from job_hunter.pipeline.scorer import score_and_filter_jobs, strategic_override_companies
from job_hunter.pipeline.tailor import run_tailor
from job_hunter.pipeline.tailorer import tailor
from job_hunter.pipeline.validator import validate
from job_hunter.sources.jd_fetcher import fetch_jd
from job_hunter.tracking.tracker import mark_processed

if TYPE_CHECKING:
    from pathlib import Path

logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))


def _today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


ROOT = str(REPO_ROOT)
JOBS_DIR = profile_path("output_dir", "outputs/jobs")
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _enrich_snippets(jobs: list[dict[str, Any]], api_cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    from job_hunter.pipeline.enrichment import enrich_snippets

    return enrich_snippets(jobs, api_cfg, fetcher=fetch_jd)


def update_readme(matches: list[dict[str, Any]]) -> None:
    write_readme_table(matches, ROOT, _today())


def _copy_latex_assets(job_dir: Path) -> None:
    _match_processor.copy_latex_assets(job_dir, profile_path)


def _screen_by_config(
    jobs: list[dict[str, Any]], scoring_cfg: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply deterministic exclusion rules from config before any LLM calls."""
    from job_hunter.pipeline.screening import screen_jobs_by_rules

    return screen_jobs_by_rules(jobs, scoring_cfg)


def _write_company_research(job: dict[str, Any], job_dir: Path) -> None:
    from job_hunter.pipeline.llm_stage import LLMStage

    _match_processor.write_company_research(
        job,
        job_dir,
        get_config=get_config,
        llm_stage_factory=LLMStage,
        logger=logger,
    )


def _make_generated_tex_self_contained(tex: str) -> str:
    return _match_processor.make_generated_tex_self_contained(tex, profile_path)


def _process_match(match: dict[str, Any]) -> bool:
    return _match_processor.process_match(
        match,
        today=_today,
        jobs_dir=JOBS_DIR,
        slugify=slugify,
        write_match_artifacts=write_match_artifacts,
        write_company_research=_write_company_research,
        tailor=tailor,
        make_tex_self_contained=_make_generated_tex_self_contained,
        copy_latex_assets=_copy_latex_assets,
        compile_tex=compile_tex,
        write_cover=write_cover,
        logger=logger,
    )


def _process_jobs(
    jobs: list[dict[str, Any]],
    *,
    skip_validate: bool,
    skip_score: bool,
    max_years: int,
    api_cfg: dict[str, Any],
    scoring_cfg: dict[str, Any],
    url_checker: Any = None,
) -> list[dict[str, Any]]:
    """
    Shared downstream pipeline: validate, score, tailor, cover, PDF.
    Returns the list of successfully processed match dicts.
    """
    jobs, config_rejected = _screen_by_config(jobs, scoring_cfg)
    for job in config_rejected:
        logger.info(
            "  Config screen rejected: %s @ %s: %s", job.get("title"), job.get("company"), job.get("_rejection_reason")
        )
    if not jobs:
        logger.warning("[pipeline] All jobs rejected by config exclusion rules.")
        return []

    if not skip_validate:
        logger.info("[pipeline] Validating %s job(s)...", len(jobs))
        jobs, rejected = validate(
            jobs,
            max_years=max_years,
            api_cfg=api_cfg,
            url_checker=url_checker or UrlLivenessCache().is_alive,
            max_years_bypass_companies=strategic_override_companies(scoring_cfg),
            excluded_industries=(scoring_cfg.get("exclusions", {}) or {}).get("industries", []),
        )
        for job in rejected:
            logger.info(
                "  Rejected: %s @ %s: %s",
                job.get("title"),
                job.get("company"),
                job.get("_rejection_reason"),
            )
        if not jobs:
            logger.warning("[pipeline] All jobs rejected during validation.")
            return []
        logger.info("[pipeline] %s job(s) passed validation", len(jobs))
    else:
        logger.info("[pipeline] Validation skipped (--skip-validate)")

    if skip_score:
        logger.info("[pipeline] Scoring skipped (--skip-score) - processing all")
        matches = [{"job": job, "score": 0, "matched_keywords": [], "gaps": []} for job in jobs]
    else:
        jobs, pre_llm_rejected = apply_pre_llm_gate(jobs, scoring_cfg)
        if pre_llm_rejected:
            logger.info("[pipeline] Pre-LLM gate dropped %s job(s)", len(pre_llm_rejected))
        if not jobs:
            logger.warning("[pipeline] Pre-LLM gate rejected all remaining jobs.")
            return []
        logger.info("[pipeline] Scoring %s job(s)...", len(jobs))
        matches = score_and_filter_jobs(jobs, config=scoring_cfg)
        if not matches:
            logger.warning("[pipeline] No jobs passed the scoring threshold.")
            return []
        logger.info("[pipeline] %s job(s) passed scoring", len(matches))

    batch_size = _configured_batch_size(scoring_cfg)
    if len(matches) > batch_size:
        matches = sorted(matches, key=lambda match: match.get("score", 0), reverse=True)
        logger.info(
            "[pipeline] Batch size: tailoring top %s of %s matched job(s)",
            batch_size,
            len(matches),
        )
        matches = matches[:batch_size]

    logger.info("[pipeline] Processing %s matched job(s)...", len(matches))
    processed = []
    for idx, match in enumerate(matches, 1):
        job = match["job"]
        logger.info(
            "[pipeline] [%s/%s] %s @ %s (score=%s)",
            idx,
            len(matches),
            job["title"],
            job["company"],
            match["score"],
        )
        try:
            if _process_match(match):
                processed.append(match)
        except Exception as e:
            logger.error("  Unexpected error: %s", e, exc_info=True)

    return processed


def _configured_batch_size(config: dict[str, Any]) -> int:
    """Return the shared agent/LLM-API batch size from canonical config."""
    scoring = config.get("scoring")
    if not isinstance(scoring, dict) or "batch_size" not in scoring:
        return DEFAULT_BATCH_SIZE
    batch_size = int(scoring["batch_size"])
    if batch_size < 1:
        raise ValueError("scoring.batch_size must be at least 1")
    return batch_size


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Job hunt pipeline - hunt or tailor specific links/text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  job-hunter hunt
  job-hunter hunt --region primary
  job-hunter tailor-links --links "https://url1, https://url2"
  job-hunter tailor-links --skip-score --force
  job-hunter tailor-raw --jd "$(cat job.txt)"
  job-hunter tailor-raw --jd - --title "Backend Engineer" --company Acme
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["hunt", "tailor-links", "tailor-raw"],
        default="hunt",
        help=(
            "hunt: scrape configured companies (default). "
            "tailor-links: process specific URLs. "
            "tailor-raw: tailor from pasted job description text."
        ),
    )
    parser.add_argument(
        "--links",
        metavar="URLS",
        help="Comma-separated job URLs for tailor-links mode. Falls back to TAILOR_LINKS env var.",
    )
    parser.add_argument(
        "--jd",
        metavar="TEXT",
        help=("Raw job description text for tailor-raw mode. Pass '-' to read from stdin."),
    )
    parser.add_argument(
        "--title",
        metavar="TITLE",
        help="Job title override for tailor-raw mode (skips LLM title extraction).",
    )
    parser.add_argument(
        "--company",
        metavar="COMPANY",
        help="Company name override for tailor-raw mode (skips LLM company extraction).",
    )
    parser.add_argument(
        "--region",
        help="Optional job_hunter.yml region key for hunt mode, e.g. primary. Omit for all enabled regions.",
    )
    parser.add_argument(
        "--depth",
        choices=("fast", "standard", "deep"),
        default="standard",
        help="Source tier depth: fast=board APIs only; standard=+ATS discovery; deep=+forced AI web search.",
    )
    hunt_split = parser.add_mutually_exclusive_group()
    hunt_split.add_argument(
        "--scrape-only",
        action="store_true",
        help="Run scrape, URL-check, and enrichment only; write snapshot and exit.",
    )
    hunt_split.add_argument(
        "--from-snapshot",
        metavar="PATH",
        help="Skip scraping; load enriched jobs from a scrape snapshot.",
    )
    parser.add_argument("--skip-score", action="store_true", help="Bypass scoring threshold")
    parser.add_argument("--skip-validate", action="store_true", help="Bypass validation checks")
    parser.add_argument("--force", action="store_true", help="Re-process already-tracked jobs")
    return parser


def _log_token_summary() -> None:
    import datetime
    import json
    import os

    from job_hunter.pipeline.llm_stage import get_token_totals

    totals = get_token_totals()
    if not totals:
        return
    logger.info("TOKEN USAGE SUMMARY")
    logger.info("%-20s %10s %10s %10s", "stage", "input", "output", "cached")
    logger.info("%s", "-" * 52)
    grand: dict[str, int] = {"in": 0, "out": 0, "cached": 0}
    for role in ("jd_extraction", "validation", "scoring", "tailoring", "cover_letter", "research"):
        t = totals.get(role)
        if not t:
            continue
        logger.info("%-20s %10d %10d %10d", role, t["in"], t["out"], t["cached"])
        for k in grand:
            grand[k] += t[k]
    logger.info("%s", "-" * 52)
    logger.info("%-20s %10d %10d %10d", "TOTAL", grand["in"], grand["out"], grand["cached"])
    if path := os.environ.get("TOKEN_LOG"):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.datetime.utcnow().isoformat(), "totals": totals}) + "\n")


def run(args: dict) -> int:
    from job_hunter.pipeline.llm_stage import reset_token_totals

    logger.info("\n%s", "=" * 60)
    region_label = args["region"] if args["mode"] == "hunt" and args["region"] else "all"
    logger.info("Pipeline | mode=%s | region=%s | %s", args["mode"], region_label, _today())
    logger.info("%s", "=" * 60)

    reset_token_totals()
    api_cfg = load_api_config()
    url_liveness = UrlLivenessCache()
    scoring_cfg = get_config("job_hunter")
    max_years = scoring_cfg.get("scoring", {}).get("max_years_experience_required", 4)

    if args["mode"] == "hunt":
        if args["scrape_only"]:
            snapshot_path, count, _stats = run_hunt_scrape_only(
                args["region"],
                REPO_ROOT,
                api_cfg,
                url_liveness.is_alive,
                depth=args.get("depth", "standard"),
            )
            print(f"snapshot_path={snapshot_path.as_posix()}")
            print(f"candidate_count={count}")
            print(f"has_candidates={str(count > 0).lower()}")
            return 0

        if args["from_snapshot"]:
            jobs, existing_urls, existing_titles = load_hunt_snapshot(args["from_snapshot"])
            if not jobs:
                logger.warning("[pipeline] Snapshot has no jobs. Exiting.")
                return 0
        else:
            jobs, existing_urls, existing_titles = run_hunt(args, api_cfg, scoring_cfg, url_liveness)
        if not jobs:
            return 0

    elif args["mode"] == "tailor-links":
        raw_links = args["links"] or os.environ.get("TAILOR_LINKS", "")
        if not raw_links:
            logger.error(
                "[pipeline] No URLs provided. Use --links 'URL1, URL2' or set the TAILOR_LINKS environment variable."
            )
            return 1
        jobs, existing_urls, existing_titles = run_tailor(args, api_cfg, scoring_cfg, url_liveness)
        if not jobs:
            logger.warning("[pipeline] No jobs fetched. Exiting.")
            return 2

    else:  # tailor-raw
        if not args["jd"]:
            logger.error("[pipeline] No job description provided. Use --jd 'TEXT' or --jd - to read from stdin.")
            return 1
        jobs, existing_urls, existing_titles = run_tailor(args, api_cfg, scoring_cfg, url_liveness)
        if not jobs:
            logger.warning("[pipeline] No jobs parsed. Exiting.")
            return 2

    logger.info("[pipeline] %s job(s) ready for processing", len(jobs))

    processed = _process_jobs(
        jobs,
        skip_validate=args["skip_validate"],
        skip_score=args["skip_score"],
        max_years=max_years,
        api_cfg=api_cfg,
        scoring_cfg=scoring_cfg,
        url_checker=url_liveness.is_alive,
    )

    if processed:
        logger.info("[pipeline] Updating README and tracker...")
        update_readme(processed)
        mark_processed([match["job"] for match in processed], existing_urls)

    logger.info("\n%s", "=" * 60)
    logger.info("[pipeline] Done. %s job(s) processed.", len(processed))
    _log_token_summary()
    logger.info("%s\n", "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run(vars(_build_parser().parse_args())))
