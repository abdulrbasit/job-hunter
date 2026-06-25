"""Company browser hunt: runs the career-page extraction ladder per company in career_pages.yml."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from job_hunter.config.loader import ROOT
from job_hunter.sources.career_pages import extract_career_page_jobs

logger = logging.getLogger(__name__)


def run() -> int:
    root = Path(ROOT)
    companies_path = root / "config" / "career_pages.yml"
    config_path = root / "config" / "job_hunter.yml"

    if not companies_path.exists():
        logger.error("[browser-hunt] %s not found — create it from the template", companies_path)
        return 1

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    companies_cfg = yaml.safe_load(companies_path.read_text(encoding="utf-8")) or {}

    titles = cfg.get("job_titles", [])
    exclusions = (cfg.get("exclusions") or {}).get("title_terms", [])
    companies = companies_cfg.get("companies") or []

    if not companies:
        logger.info("[browser-hunt] no companies in %s — nothing to do", companies_path)
        return 0

    out = root / "outputs" / "browser_hunt"
    out.mkdir(parents=True, exist_ok=True)

    all_jobs: list[dict] = []
    for company in companies:
        jobs = extract_career_page_jobs(company, titles, exclusions)
        all_jobs.extend(jobs)
        logger.info("[browser-hunt] %s: %d jobs", company.get("name", "?"), len(jobs))

    (out / "jobs.json").write_text(
        json.dumps(all_jobs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("[browser-hunt] total=%d → %s", len(all_jobs), out / "jobs.json")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(run())
