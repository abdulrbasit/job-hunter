"""
Tracks processed job URLs to avoid duplicate processing across daily runs.
Uses jobs.db as persistent URL-only dedup storage.
Dedup is URL-only: same company with a different URL is never blocked.
"""

from __future__ import annotations

from job_hunter.config.loader import ROOT as REPO_ROOT
from job_hunter.db.jobs import get_all_known_urls, insert_candidate_urls, mark_urls_processed
from job_hunter.sources.search_providers import canonicalize_url


def load_processed() -> set[str]:
    """Load all known job URLs from DB — used by filter_new_jobs for scrape dedup."""
    return get_all_known_urls(REPO_ROOT)


def save_processed(urls: set[str]) -> None:
    """Ensure URLs are recorded in DB as discovered (no-op if already present)."""
    insert_candidate_urls(REPO_ROOT, urls)


def filter_new_jobs(jobs: list[dict]) -> tuple[list[dict], set[str]]:
    """Remove jobs already discovered in previous runs by URL."""
    processed_urls = load_processed()
    new_jobs = []
    skipped = 0

    for job in jobs:
        url = job.get("url", "")
        if url and canonicalize_url(url) in processed_urls:
            print(f"  [tracker] Already processed (URL): {job['title'][:50]} @ {job['company']}")
            skipped += 1
        else:
            new_jobs.append(job)

    if skipped:
        print(f"[tracker] Skipped {skipped} already-processed jobs")
    print(f"[tracker] {len(new_jobs)} new jobs to process")
    return new_jobs, processed_urls


def mark_processed(jobs: list[dict], existing_urls: set[str]) -> None:
    """Add newly processed job URLs to DB."""
    new_urls = {canonicalize_url(j["url"]) for j in jobs if j.get("url")}
    mark_urls_processed(REPO_ROOT, new_urls)
    print(f"[tracker] Marked {len(new_urls)} URLs processed")
