"""Shared read/write helpers for outputs/state/discovered_urls.yml."""

from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.sources.search_providers import canonicalize_url

_HEADER = (
    "# URL-only dedup state. Each entry is a canonical job URL.\n"
    "# discovered: jobs already surfaced/processed by Job Hunter.\n"
    "# candidate_urls: broad-discovery URLs already seen by search/AI discovery.\n"
    "# Remove a URL manually to rediscover or reprocess that job.\n\n"
)


def _read_state(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _write_state(path: str | Path, discovered: set[str], candidate_urls: set[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        _HEADER
        + yaml.safe_dump(
            {
                "discovered": sorted(canonicalize_url(u) for u in discovered if u),
                "candidate_urls": sorted(canonicalize_url(u) for u in candidate_urls if u),
            },
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
