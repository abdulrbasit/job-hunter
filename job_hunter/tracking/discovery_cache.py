"""Caches broad-discovery candidate URLs in the unified URL state file.

The cache supports two formats:

  Legacy flat format (list of URL strings):
    candidate_urls:
      - https://...

  Rich format (list of objects with url + optional metadata):
    candidate_urls:
      - url: https://...
        title: "..."
        company: "..."
        posted: "..."
        snippet: "..."

Both formats are read transparently. Writes always use the flat format so the
file stays small and diff-friendly. Metadata is only used during cache
revalidation when the scraper needs to reconstruct a minimal job dict.
"""

from __future__ import annotations

import os

from job_hunter.core.config import ROOT as REPO_ROOT
from job_hunter.sources.search_providers import canonicalize_url
from job_hunter.tracking._io import _read_state, _write_state

ROOT = str(REPO_ROOT)
CACHE_FILE = os.path.join(ROOT, "outputs", "state", "discovered_urls.yml")


def _iter_cache_entries(data: dict) -> list:
    """Return raw entries from the candidate_urls list regardless of format."""
    return (data.get("candidate_urls", []) or []) + (data.get("discovered", []) or [])


def load_cached_candidate_urls() -> set[str]:
    """Return the set of canonicalized URLs already seen by broad discovery."""
    data = _read_state(CACHE_FILE)
    result = set()
    for entry in _iter_cache_entries(data):
        if isinstance(entry, str):
            url = entry
        elif isinstance(entry, dict):
            url = entry.get("url", "")
        else:
            continue
        if url:
            result.add(canonicalize_url(url))
    return result


def load_cached_candidate_urls_with_metadata() -> dict[str, dict]:
    """Return a mapping of canonicalized URL -> metadata dict.

    The metadata dict may be empty for flat-format entries. Keys that may be
    present: ``title``, ``company``, ``posted``, ``snippet``.

    Used by the cache revalidation fallback so it can reconstruct a minimal
    job dict without re-fetching every cached URL.
    """
    data = _read_state(CACHE_FILE)
    result: dict[str, dict] = {}
    for entry in _iter_cache_entries(data):
        if isinstance(entry, str):
            canonical = canonicalize_url(entry)
            if canonical:
                result[canonical] = {}
        elif isinstance(entry, dict):
            url = entry.get("url", "")
            if not url:
                continue
            canonical = canonicalize_url(url)
            if canonical:
                result[canonical] = {k: entry[k] for k in ("title", "company", "posted", "snippet") if k in entry}
    return result


def save_cached_candidate_urls(urls: set[str]) -> None:
    existing = _read_state(CACHE_FILE)
    discovered = set(existing.get("discovered", []) or [])
    _write_state(CACHE_FILE, discovered, urls)
