"""Snapshot write/read — decouples scrape from score.

--scrape-only: scrape → enrich → snapshot.write() → exit
--from-snapshot <path>: snapshot.read() → score → tailor → ...
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from job_hunter.models import JobPosting, ScrapeStats, SnapshotPayload

logger = logging.getLogger(__name__)


def write(jobs: list[JobPosting], region_key: str, stats: ScrapeStats, output_dir: Path) -> Path:
    """Serialise jobs to a timestamped JSON snapshot and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"snapshot_{region_key}_{ts}.json"

    payload = SnapshotPayload(
        jobs=jobs,
        region_key=region_key,
        stats=stats,
        created_at=datetime.now(UTC).isoformat(),
    )
    path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    logger.info("[snapshot] wrote %d jobs to %s", len(jobs), path)
    return path


def read(path: Path) -> SnapshotPayload:
    """Load a snapshot from disk. Raises FileNotFoundError or ValidationError on bad input."""
    if not path.exists():
        raise FileNotFoundError(f"Snapshot not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = SnapshotPayload.model_validate(data)
    logger.info("[snapshot] loaded %d jobs from %s (region=%s)", len(payload.jobs), path, payload.region_key)
    return payload
