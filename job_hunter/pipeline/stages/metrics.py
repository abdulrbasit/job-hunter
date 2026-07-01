"""Run metrics: persistence to metrics.db and token-usage summary logging."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from job_hunter.pipeline.context import PipelineRunContext

logger = logging.getLogger(__name__)


def persist_metrics(ctx: PipelineRunContext, jobs_found: int, jobs_tailored: int, *, elapsed: float) -> None:
    try:
        from job_hunter.config.loader import ROOT as REPO_ROOT
        from job_hunter.config.loader import get_mode
        from job_hunter.llm.token_usage import get_token_totals
        from job_hunter.metrics.store import record_run

        db_path = REPO_ROOT / "outputs" / "state" / "metrics.db"
        record_run(
            db_path,
            ts=ctx.start_ts,
            mode=ctx.options.mode,
            exec_mode=get_mode(),
            region=ctx.options.region or "",
            duration_s=round(elapsed, 2),
            jobs_found=jobs_found,
            jobs_tailored=jobs_tailored,
            token_totals=get_token_totals(),
            total_cost_usd=None,
            scrape_stats={},  # ponytail: add ScrapeStats passthrough when needed
        )
    except Exception:  # noqa: BLE001,S110
        pass


def log_token_summary() -> None:
    import datetime
    import json
    import os

    from job_hunter.llm.token_usage import get_token_totals

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
            f.write(json.dumps({"ts": datetime.datetime.now(datetime.UTC).isoformat(), "totals": totals}) + "\n")
