"""Company browser hunt: runs the career-page extraction ladder per company in career_pages.yml.

Writes results to outputs/state/jobs.db (status='candidate'), the same store the regular
find-jobs hunt uses — so browser-hunt candidates get deduped, screened, scored, and tailored
through the exact same downstream pipeline, not a separate isolated file.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from job_hunter.config.loader import ROOT
from job_hunter.sources.career_pages import extract_career_page_jobs
from job_hunter.tracking.repository import insert_jobs

logger = logging.getLogger(__name__)


def run() -> int:
    root = Path(ROOT)
    companies_path = root / "config" / "career_pages.yml"
    config_path = root / "config" / "job_hunter.yml"

    if not companies_path.exists():
        logger.error("[browser-hunt] %s not found — create it from the template", companies_path)
        return 1

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    companies_config = yaml.safe_load(companies_path.read_text(encoding="utf-8")) or {}

    titles = config.get("job_titles", [])
    exclusions = (config.get("exclusions") or {}).get("title_terms", [])
    companies = companies_config.get("companies") or []

    if not companies:
        logger.info("[browser-hunt] no companies in %s — nothing to do", companies_path)
        return 0

    all_jobs: list[dict] = []
    for company in companies:
        jobs = extract_career_page_jobs(company, titles, exclusions)
        all_jobs.extend(jobs)
        logger.info("[browser-hunt] %s: %d jobs", company.get("name", "?"), len(jobs))

    if all_jobs:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        inserted = insert_jobs(root, all_jobs, run_id=run_id)
        logger.info("[browser-hunt] total=%d → jobs.db (run_id=%s)", inserted, run_id)
    else:
        logger.info("[browser-hunt] total=0 — nothing to write")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(run())
