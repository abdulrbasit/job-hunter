"""tailor-raw mode: parse a single job description pasted or piped in as raw text."""

from __future__ import annotations

import dataclasses
import logging

from job_hunter.pipeline.context import ModeOutcome, PipelineResult, PipelineRunContext
from job_hunter.pipeline.tailor import run_tailor

logger = logging.getLogger(__name__)


def execute(ctx: PipelineRunContext) -> ModeOutcome:
    options = ctx.options
    if not options.jd:
        logger.error("[pipeline] No job description provided. Use --jd 'TEXT' or --jd - to read from stdin.")
        return ModeOutcome(early_result=PipelineResult(exit_code=1))

    jobs, existing_urls, existing_titles = run_tailor(
        dataclasses.asdict(options), ctx.api_config, ctx.scoring_config, ctx.url_liveness
    )
    if not jobs:
        logger.warning("[pipeline] No jobs parsed. Exiting.")
        return ModeOutcome(early_result=PipelineResult(exit_code=2))

    return ModeOutcome(jobs=jobs, existing_urls=existing_urls, existing_titles=existing_titles)
