"""Mode-aware CLI dispatch.

Reads config/job_hunter.yml → mode at startup and routes `hunt` and
`tailor` commands accordingly:

  agent:   scrape + enrich + snapshot; agent skills drive scoring/tailoring
  llm-api: full autonomous pipeline (scrape → score → tailor → PDF)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


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
    from job_hunter.models import HuntInput
    from job_hunter.pipeline.hunt import run

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
    if result.snapshot_path:
        print(f"[hunt] snapshot: {result.snapshot_path}")
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
    from job_hunter.config import get_mode
    from job_hunter.core.config import ROOT, get_config, load_api_config
    from job_hunter.core.url_liveness import UrlLivenessCache
    from job_hunter.pipeline.orchestrator import run as orch_run
    from job_hunter.pipeline.tailor import run_tailor

    mode = get_mode()
    logger.info("[dispatch] tailor — mode=%s links=%s", mode, bool(links))

    if links:
        ns = {
            "mode": "tailor-links",
            "links": links,
            "jd": None,
            "title": title,
            "company": company,
            "force": force,
            "region": None,
            "depth": "standard",
            "scrape_only": False,
            "from_snapshot": None,
            "skip_score": False,
            "skip_validate": False,
        }
    else:
        ns = {
            "mode": "tailor-raw",
            "links": None,
            "jd": jd_text,
            "title": title,
            "company": company,
            "force": force,
            "region": None,
            "depth": "standard",
            "scrape_only": False,
            "from_snapshot": None,
            "skip_score": False,
            "skip_validate": False,
        }

    if mode == "agent":
        jobs, existing_urls, existing_titles = run_tailor(
            ns,
            load_api_config(),
            get_config("job_hunter"),
            UrlLivenessCache(),
        )
        today = datetime.today().strftime("%Y-%m-%d")
        path = ROOT / "outputs" / "candidates" / f"{today}_tailor_candidates.json"
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

    orch_run(ns)
