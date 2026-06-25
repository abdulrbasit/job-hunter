"""Briefing and LinkedIn weekly context helpers."""

from __future__ import annotations

import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from job_hunter.agent_context._utils import (
    _read_json_or_yaml,
    _read_yaml,
    _root,
)
from job_hunter.agent_context.candidates import (
    _candidate_files,
    _jobs_from_candidate_file,
    build_candidate_queue,
)
from job_hunter.agent_context.stories import story_index


def _latest_commit_subject(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],  # noqa: S607
            cwd=root,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return "unknown"
    return result.stdout.strip() or "unknown"


def brief_context(*, root: Path | None = None) -> str:
    base = _root(root)
    subject = _latest_commit_subject(base)
    discovery = "yes" if "discovery" in subject.lower() else "no"
    queue = build_candidate_queue(root=base, today_only=False, limit=10000)
    candidate_lines = []
    for path in _candidate_files(base):
        try:
            jobs = _jobs_from_candidate_file(path)
            candidate_lines.append(f"- `{path.name}`: {len(jobs)} candidates")
        except Exception:
            candidate_lines.append(f"- `{path.name}`: unreadable")
    if not candidate_lines:
        candidate_lines.append("- none")

    today = date.today().isoformat()
    jobs_dir = base / "outputs" / "jobs"
    today_rows: list[str] = []
    if jobs_dir.exists():
        for folder in sorted(jobs_dir.iterdir()):
            if not folder.is_dir():
                continue
            meta = _read_json_or_yaml(folder / "meta.json") if (folder / "meta.json").exists() else {}
            if not (folder.name.startswith(today) or meta.get("date") == today):
                continue
            score = _read_yaml(folder / "score.yml")
            today_rows.append(
                "| {folder} | {company} | {title} | {score} | {decision} |".format(
                    folder=folder.name,
                    company=meta.get("company", ""),
                    title=meta.get("title", ""),
                    score=score.get("score", ""),
                    decision=score.get("decision", score.get("status", "")),
                )
            )

    jobs_table = "\n".join(today_rows) if today_rows else "No job folders created today."
    candidate_summary = "\n".join(candidate_lines[:20])
    if len(candidate_lines) > 20:
        candidate_summary += f"\n- ... {len(candidate_lines) - 20} more file(s)"

    return f"""# Agent Brief - {today}

Latest commit: {subject}
Discovery commit: {discovery}

## Candidate Snapshots
{candidate_summary}

Unprocessed queue: {queue["count"]} candidate(s) from {len(queue["source_files"])} file(s).

## Today's Jobs
| Folder | Company | Title | Score | Decision |
|---|---|---|---|---|
{jobs_table}

Next:
- Run `/job-hunter batch` when candidates are ready.
- Run `/job-hunter one <url>` for a single posting.
"""


def _linkedin_job_limit(root: Path, days: int, limit: int | None) -> tuple[int, str]:
    if limit is not None and limit > 0:
        return limit, "cli"
    scoring = _read_yaml(root / "config" / "job_hunter.yml").get("scoring", {})
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
            score = _read_yaml(folder / "score.yml")
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
