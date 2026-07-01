"""hunt mode: scrape-only snapshot, from-snapshot load, or full scrape+dedup+enrich."""

from __future__ import annotations

import dataclasses
import logging

from job_hunter.pipeline.context import ModeOutcome, PipelineResult, PipelineRunContext
from job_hunter.pipeline.hunt import load_hunt_snapshot, run_hunt, run_hunt_scrape_only

logger = logging.getLogger(__name__)


def execute(ctx: PipelineRunContext) -> ModeOutcome:
    options = ctx.options

    if options.scrape_only:
        from job_hunter.config.loader import ROOT as REPO_ROOT

        snapshot_path, count, _stats = run_hunt_scrape_only(
            options.region, REPO_ROOT, ctx.api_config, ctx.url_liveness.is_alive, depth=options.depth
        )
        print(f"snapshot_path={snapshot_path.as_posix()}")
        print(f"candidate_count={count}")
        print(f"has_candidates={str(count > 0).lower()}")
        return ModeOutcome(early_result=PipelineResult(exit_code=0))

    if options.from_snapshot:
        jobs, existing_urls, existing_titles = load_hunt_snapshot(options.from_snapshot)
        if not jobs:
            logger.warning("[pipeline] Snapshot has no jobs. Exiting.")
            return ModeOutcome(early_result=PipelineResult(exit_code=0))
    else:
        jobs, existing_urls, existing_titles = run_hunt(
            dataclasses.asdict(options), ctx.api_config, ctx.scoring_config, ctx.url_liveness
        )

    if not jobs:
        return ModeOutcome(early_result=PipelineResult(exit_code=0))

    return ModeOutcome(jobs=jobs, existing_urls=existing_urls, existing_titles=existing_titles)
