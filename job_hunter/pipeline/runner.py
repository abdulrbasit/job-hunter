"""
Pipeline runner — typed mode dispatch.

Two modes, one entry point:

  hunt (default)   Search all enabled job sources and boards for configured titles.
                   Runs daily via GitHub Actions.

  tailor-links     Tailor resume for a specific list of URLs.
  tailor-raw       Tailor resume from pasted job description text.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

from job_hunter.config.loader import ROOT as REPO_ROOT
from job_hunter.config.loader import get_api_config, get_config, setup_logging
from job_hunter.config.reference_data import resolve_max_years_experience
from job_hunter.core.url_liveness import UrlLivenessCache
from job_hunter.pipeline.context import PipelineCommandOptions, PipelineResult, PipelineRunContext
from job_hunter.pipeline.modes import hunt as hunt_mode
from job_hunter.pipeline.modes import tailor_links as tailor_links_mode
from job_hunter.pipeline.modes import tailor_raw as tailor_raw_mode
from job_hunter.pipeline.stages.metrics import log_token_summary, persist_metrics
from job_hunter.pipeline.stages.processing import finalize_processed_batch, process_jobs

logger = logging.getLogger("job_hunter")

_MODES = {
    "hunt": hunt_mode,
    "tailor-links": tailor_links_mode,
    "tailor-raw": tailor_raw_mode,
}


def _today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def run(options: PipelineCommandOptions) -> PipelineResult:
    from job_hunter.llm.token_usage import reset_token_totals

    setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))

    start_ts = datetime.now(UTC).replace(microsecond=0).isoformat()
    start_mono = time.monotonic()

    logger.info("\n%s", "=" * 60)
    region_label = options.region if options.mode == "hunt" and options.region else "all"
    logger.info("Pipeline | mode=%s | region=%s | %s", options.mode, region_label, _today())
    logger.info("%s", "=" * 60)

    reset_token_totals()
    from job_hunter.tools.compile_profile import compile_all as _compile_profile

    _compile_profile(REPO_ROOT)
    api_config = get_api_config()
    url_liveness = UrlLivenessCache()
    scoring_config = get_config("job_hunter")
    max_years = resolve_max_years_experience(scoring_config)

    ctx = PipelineRunContext(
        options=options,
        api_config=api_config,
        scoring_config=scoring_config,
        max_years=max_years,
        url_liveness=url_liveness,
        start_ts=start_ts,
        start_mono=start_mono,
    )

    outcome = _MODES[options.mode].execute(ctx)
    if outcome.early_result is not None:
        return outcome.early_result

    jobs_found = len(outcome.jobs)
    logger.info("[pipeline] %s job(s) ready for processing", jobs_found)

    processed = process_jobs(
        outcome.jobs,
        skip_validate=options.skip_validate,
        skip_score=options.skip_score,
        max_years=max_years,
        api_config=api_config,
        scoring_config=scoring_config,
        url_checker=url_liveness.is_alive,
    )

    finalize_processed_batch(processed, outcome.existing_urls)

    logger.info("\n%s", "=" * 60)
    logger.info("[pipeline] Done. %s job(s) processed.", len(processed))
    log_token_summary()
    persist_metrics(ctx, jobs_found, len(processed), elapsed=time.monotonic() - start_mono)
    logger.info("%s\n", "=" * 60)
    return PipelineResult(exit_code=0, jobs_found=jobs_found, jobs_processed=len(processed))
