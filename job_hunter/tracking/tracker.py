"""
Tracks processed job URLs to avoid duplicate processing across daily runs.
Uses outputs/state/discovered_urls.yml as persistent URL-only dedup storage.
Dedup is URL-only: same company with a different URL is never blocked.
"""

from __future__ import annotations

import os

from job_hunter.core.config import ROOT as REPO_ROOT
from job_hunter.sources.search_providers import canonicalize_url
from job_hunter.tracking._io import _read_state, _write_state

ROOT = str(REPO_ROOT)
TRACKER_FILE = os.path.join(ROOT, "outputs", "state", "discovered_urls.yml")


def load_processed() -> set[str]:
    """Load previously discovered job URLs."""
    data = _read_state(TRACKER_FILE)
    return {canonicalize_url(u) for u in data.get("discovered", []) if u}


def save_processed(urls: set[str]) -> None:
    """Save updated discovered URLs back to file."""
    existing = _read_state(TRACKER_FILE)
    candidate_urls = set(existing.get("candidate_urls", []) or [])
    _write_state(TRACKER_FILE, urls, candidate_urls)


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
    """Add newly processed job URLs to the tracker and save."""
    new_urls = {canonicalize_url(j["url"]) for j in jobs if j.get("url")}
    updated_urls = existing_urls | new_urls
    save_processed(updated_urls)
    print(f"[tracker] Saved {len(new_urls)} new URLs ({len(updated_urls)} total tracked)")
