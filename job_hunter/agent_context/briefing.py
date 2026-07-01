"""LinkedIn weekly context helper."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from job_hunter.agent_context._utils import (
    _read_json_or_yaml,
    _root,
)
from job_hunter.agent_context.stories import story_index
from job_hunter.core.utils import read_yaml


def _linkedin_job_limit(root: Path, days: int, limit: int | None) -> tuple[int, str]:
    if limit is not None and limit > 0:
        return limit, "cli"
    scoring = read_yaml(root / "config" / "job_hunter.yml").get("scoring", {})
    daily_limit = int(scoring.get("batch_size") or 0)
    if daily_limit > 0:
        return daily_limit * max(days, 1), "config:scoring.batch_size * days"
    return 0, "unlimited"


def linkedin_weekly_context(
    *,
    root: Path | None = None,
    days: int = 7,
    limit: int | None = None,
) -> dict[str, Any]:
    base = _root(root)
    job_limit, limit_source = _linkedin_job_limit(base, days, limit)
    cutoff = datetime.now() - timedelta(days=days)
    jobs: list[dict[str, Any]] = []
    jobs_dir = base / "outputs" / "jobs"
    if jobs_dir.exists():
        for folder in sorted(jobs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not folder.is_dir() or datetime.fromtimestamp(folder.stat().st_mtime) < cutoff:
                continue
            meta = _read_json_or_yaml(folder / "meta.json") if (folder / "meta.json").exists() else {}
            score = read_yaml(folder / "score.yml")
            jobs.append(
                {
                    "slug": folder.name,
                    "company": meta.get("company", ""),
                    "title": meta.get("title", ""),
                    "score": score.get("score", ""),
                    "decision": score.get("decision", score.get("status", "")),
                }
            )
            if job_limit and len(jobs) >= job_limit:
                break
    return {
        "days": days,
        "job_limit": job_limit or None,
        "job_limit_source": limit_source,
        "jobs": jobs,
        "story_index": story_index(root=base),
    }
