"""CLI-only run-artifact helpers, plus re-exports of job_hunter.workspace.finalize for the
existing `job_hunter.cli._run_artifacts` import path. The finalize bookkeeping itself lives
in workspace/finalize.py so job_hunter.ux can call it without depending on job_hunter.cli
(the composition root) — see tests/test_dependency_boundaries.py.
"""

from __future__ import annotations

from job_hunter.workspace.finalize import (  # noqa: F401 — re-exported for existing callers
    FINALIZE_PATHS,
    TRANSIENT_STATE_PATHS,
    cleanup_transient_state,
    derive_finalize_message,
    discard_dead_job_folders,
    discard_job_folder,
    run_finalize_core,
    stage_and_commit_finalize_paths,
    sync_processed_from_job_outputs,
    validate_run_artifacts,
)


def expand_listing_candidate(url: str, company: str, location: str, title: str) -> dict | None:
    from job_hunter.config import get_config
    from job_hunter.config.reference_data import resolve_title_exclusions
    from job_hunter.sources.search import fetch_playwright_career_jobs

    search_config = get_config("job_hunter")
    title_filters = search_config.get("job_titles", [])
    excluded_terms = resolve_title_exclusions(search_config)
    try:
        jobs = fetch_playwright_career_jobs(
            {"name": company or "Unknown Company", "career_url": url, "location": location},
            title_filters,
            excluded_terms,
        )
    except Exception:
        return None
    if not jobs:
        return None
    wanted = title.lower().strip()
    for job in jobs:
        found = str(job.get("title") or "").lower()
        if wanted and (wanted in found or found in wanted):
            return job
    return jobs[0] if len(jobs) == 1 else None
