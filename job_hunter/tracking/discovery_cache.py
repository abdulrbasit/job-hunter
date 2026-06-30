"""Caches broad-discovery candidate URLs in jobs.db.

Replaces the YAML-backed candidate_urls list in discovered_urls.yml.
"""

from __future__ import annotations

from job_hunter.config.loader import ROOT as REPO_ROOT
from job_hunter.db.jobs import (
    get_candidate_urls,
    get_candidate_urls_with_metadata,
    insert_candidate_urls,
)
from job_hunter.sources.search_providers import canonicalize_url


def load_cached_candidate_urls() -> set[str]:
    """Return the set of canonicalized URLs already seen by broad discovery."""
    return get_candidate_urls(REPO_ROOT)


def load_cached_candidate_urls_with_metadata() -> dict[str, dict]:
    """Return a mapping of canonicalized URL -> metadata dict."""
    return get_candidate_urls_with_metadata(REPO_ROOT)


def save_cached_candidate_urls(urls: set[str]) -> None:
    """Persist broad-discovery URLs to DB."""
    canonical_urls = {canonicalize_url(u) for u in urls if u}
    insert_candidate_urls(REPO_ROOT, canonical_urls)
