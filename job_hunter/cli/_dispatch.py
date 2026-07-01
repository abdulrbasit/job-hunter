"""Mode-aware CLI dispatch.

Reads config/job_hunter.yml → mode at startup and routes `hunt` and
`tailor` commands accordingly:

  agent:   scrape + enrich + snapshot; agent skills drive scoring/tailoring
  llm-api: full autonomous pipeline (scrape → score → tailor → PDF)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _tailor_snapshot_path(root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    return root / "outputs" / "candidates" / f"{timestamp}_tailor_candidates.json"


def dispatch_hunt(
    region_key: str | None = None,
    *,
    depth: str = "standard",
    scrape_only: bool = False,
    from_snapshot: str | None = None,
    skip_score: bool = False,
    skip_validate: bool = False,
    force: bool = False,
) -> None:
    """Entry point for `job-hunter hunt`. Reads mode from config and routes."""
    from job_hunter.config import get_mode
    from job_hunter.config.loader import setup_logging
    from job_hunter.models import HuntInput
    from job_hunter.pipeline.hunt import run

    setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))
    mode = get_mode()
    resolved_key = region_key or "all"
    logger.info("[dispatch] hunt — mode=%s region=%s", mode, resolved_key)

    inp = HuntInput(
        region_key=resolved_key,
        mode=mode,
        from_snapshot=Path(from_snapshot) if from_snapshot else None,
        scrape_only=scrape_only,
        skip_score=skip_score,
        skip_validate=skip_validate,
        force=force,
    )
    result = run(inp)

    print(
        f"\n[hunt] mode={result.mode} fetched={result.stats.total_fetched} "
        f"duration={result.stats.duration_seconds:.1f}s"
    )
    print(f"run_id={result.run_id}")
    print(f"candidate_count={result.stats.total_after_policy}")
    print(f"has_candidates={str(result.stats.total_after_policy > 0).lower()}")
    if result.mode == "agent":
        print("[hunt] Ready for agent skills -> run /job-hunter batch or /job-hunter one <url>")


def dispatch_tailor(
    *,
    links: str | None = None,
    jd_text: str | None = None,
    title: str | None = None,
    company: str | None = None,
    force: bool = False,
) -> None:
    """Entry point for `job-hunter tailor`. Routes to pipeline or agent mode."""
    import dataclasses

    from job_hunter.config import get_mode
    from job_hunter.config.loader import ROOT, get_api_config, get_config
    from job_hunter.core.url_liveness import UrlLivenessCache
    from job_hunter.pipeline.context import PipelineCommandOptions
    from job_hunter.pipeline.runner import run as orch_run
    from job_hunter.pipeline.tailor import run_tailor

    mode = get_mode()
    logger.info("[dispatch] tailor — mode=%s links=%s", mode, bool(links))

    if links:
        options = PipelineCommandOptions(mode="tailor-links", links=links, title=title, company=company, force=force)
    else:
        options = PipelineCommandOptions(mode="tailor-raw", jd=jd_text, title=title, company=company, force=force)

    if mode == "agent":
        jobs, existing_urls, existing_titles = run_tailor(
            dataclasses.asdict(options),
            get_api_config(),
            get_config("job_hunter"),
            UrlLivenessCache(),
            use_llm=False,
        )
        today = datetime.today().strftime("%Y-%m-%d")
        path = _tailor_snapshot_path(ROOT)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "date": today,
            "region": "manual",
            "count": len(jobs),
            "jobs": jobs,
            "existing_urls": sorted(existing_urls),
            "existing_titles": sorted(existing_titles),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"snapshot_path={path.as_posix()}")
        print(f"candidate_count={len(jobs)}")
        print(f"has_candidates={str(bool(jobs)).lower()}")
        print("[tailor] Ready for agent skills -> run /job-hunter batch")
        return

    orch_run(options)
