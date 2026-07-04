"""Company browser hunt: runs the career-page extraction ladder per company in career_pages.yml.

Writes results to outputs/state/jobs.db (status='candidate'), the same store the regular
find-jobs hunt uses — so browser-hunt candidates get deduped, screened, scored, and tailored
through the exact same downstream pipeline, not a separate isolated file.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from job_hunter.config.loader import ROOT
from job_hunter.pipeline.stages.screening import screen_jobs_by_rules
from job_hunter.sources.career_pages import extract_career_page_jobs
from job_hunter.sources.career_pages._rendering import ensure_chromium_installed
from job_hunter.tracking.repository import insert_jobs

logger = logging.getLogger(__name__)

Progress = Callable[[dict[str, Any]], None]


def _friendly_reason(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "took too long to respond"
    if "connection" in name:
        return "couldn't be reached"
    return "couldn't be checked right now"


def run(*, on_progress: Progress | None = None) -> int:
    emit = on_progress or (lambda _event: None)
    root = Path(ROOT)
    companies_path = root / "config" / "career_pages.yml"
    config_path = root / "config" / "job_hunter.yml"

    if not companies_path.exists():
        logger.error("[browser-hunt] %s not found — create it from the template", companies_path)
        emit({"step": "fatal", "reason": "no company list found — add companies in config/career_pages.yml"})
        return 1

    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        companies_config = yaml.safe_load(companies_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        logger.exception("[browser-hunt] failed to read config")
        emit({"step": "fatal", "reason": "config/career_pages.yml or config/job_hunter.yml could not be read"})
        return 1

    titles = config.get("job_titles", [])
    exclusions = (config.get("exclusions") or {}).get("title_terms", [])
    companies = companies_config.get("companies") or []

    if not companies:
        logger.info("[browser-hunt] no companies in %s — nothing to do", companies_path)
        return 0

    ensure_chromium_installed()

    total = len(companies)
    emit({"step": "started", "total": total})
    succeeded = failed = 0
    all_jobs: list[dict] = []
    for i, company in enumerate(companies, start=1):
        name = company.get("name", "?") if isinstance(company, dict) else str(company)
        emit({"step": "company-checking", "index": i, "total": total, "company": name})
        try:
            jobs = extract_career_page_jobs(company, titles, exclusions)
        except Exception as exc:  # noqa: BLE001 - one bad company must never abort the rest
            failed += 1
            reason = _friendly_reason(exc)
            logger.warning("[browser-hunt] %s: failed (%s)", name, exc)
            emit({"step": "company-failed", "index": i, "total": total, "company": name, "reason": reason})
            continue
        succeeded += 1
        all_jobs.extend(jobs)
        logger.info("[browser-hunt] %s: %d jobs", name, len(jobs))
        emit({"step": "company-done", "index": i, "total": total, "company": name, "jobs_found": len(jobs)})

    kept, rejected = screen_jobs_by_rules(all_jobs, config)
    if rejected:
        logger.info("[browser-hunt] %d jobs excluded by policy before insert", len(rejected))

    if kept:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        inserted = insert_jobs(root, kept, run_id=run_id)
        logger.info("[browser-hunt] total=%d → jobs.db (run_id=%s)", inserted, run_id)
    else:
        inserted = 0
        logger.info("[browser-hunt] total=0 — nothing to write")

    emit({"step": "finished", "total": total, "succeeded": succeeded, "failed": failed, "jobs_found": inserted})
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(run())
