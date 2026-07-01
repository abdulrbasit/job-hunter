"""tailor-links mode: fetch JDs from a comma/newline-separated list of URLs."""

from __future__ import annotations

import dataclasses
import logging
import os

from job_hunter.pipeline.context import ModeOutcome, PipelineResult, PipelineRunContext
from job_hunter.pipeline.tailor import run_tailor

logger = logging.getLogger(__name__)


def execute(ctx: PipelineRunContext) -> ModeOutcome:
    options = ctx.options
    raw_links = options.links or os.environ.get("TAILOR_LINKS", "")
    if not raw_links:
        logger.error(
            "[pipeline] No URLs provided. Use --links 'URL1, URL2' or set the TAILOR_LINKS environment variable."
        )
        return ModeOutcome(early_result=PipelineResult(exit_code=1))

    jobs, existing_urls, existing_titles = run_tailor(
        dataclasses.asdict(options), ctx.api_config, ctx.scoring_config, ctx.url_liveness
    )
    if not jobs:
        logger.warning("[pipeline] No jobs fetched. Exiting.")
        return ModeOutcome(early_result=PipelineResult(exit_code=2))

    return ModeOutcome(jobs=jobs, existing_urls=existing_urls, existing_titles=existing_titles)
