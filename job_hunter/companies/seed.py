"""Loads the bundled per-country company seed (package resource, not user-editable)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from importlib import resources
from typing import Any

from job_hunter.models import Company


@lru_cache(maxsize=1)
def manifest() -> dict[str, Any]:
    raw = resources.files("job_hunter.companies").joinpath("data", "manifest.json").read_text(encoding="utf-8")
    return json.loads(raw)


def iter_seed_rows() -> Iterator[tuple[str, str, str, str, str | None]]:
    """Yield (catalog_id, name, url, country, industry) across every shard.

    Not cached — shards are read once per re-seed (a rare, versioned event), and
    caching every row would hold the full 100k-per-country dataset in memory.
    """
    data_dir = resources.files("job_hunter.companies").joinpath("data")
    for country in sorted(manifest()["files"]):
        text = data_dir.joinpath(f"{country}.jsonl").read_text(encoding="utf-8")
        for line in text.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            yield row["id"], row["name"], row["url"], country, row.get("industry") or "other"


def iter_seed_companies() -> Iterator[Company]:
    """Yield full package-owned company rows while keeping iter_seed_rows compatible."""
    data_dir = resources.files("job_hunter.companies").joinpath("data")
    for country in sorted(manifest()["files"]):
        text = data_dir.joinpath(f"{country}.jsonl").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.strip():
                row = json.loads(line)
                yield Company(
                    catalog_id=row["id"],
                    name=row["name"],
                    career_url=row["url"],
                    country=country,
                    industry=row.get("industry") or "other",
                    company_type=row.get("company_type") or "unknown",
                    funding_stage=row.get("funding_stage"),
                )
