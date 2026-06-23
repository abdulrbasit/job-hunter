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
from job_hunter.config.defaults import EXCLUDED_LISTING_URL_PATTERNS, STALE_INDICATORS
from job_hunter.constants import DEFAULT_BATCH_SIZE


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


def _effective_region_titles(region_config: dict[str, Any], global_titles: list[str]) -> list[str]:
    titles = region_config.get("job_titles") or global_titles
    return [str(title) for title in titles if str(title).strip()]


def _llm_search_regions(config: dict[str, Any]) -> list[dict[str, Any]]:
    global_titles = [str(title) for title in config.get("job_titles", []) or [] if str(title).strip()]
    regions: list[dict[str, Any]] = []
    for region_name, region_config in (config.get("regions") or {}).items():
        if not isinstance(region_config, dict) or not region_config.get("enabled", True):
            continue
        regions.append(
            {
                "region": str(region_name),
                "country": str(region_config.get("country") or ""),
                "location": str(region_config.get("location") or ""),
                "search_lang": str(region_config.get("search_lang") or ""),
                "primary": bool(region_config.get("primary", False)),
                "job_titles": _effective_region_titles(region_config, global_titles),
            }
        )
    return regions


def llm_search_config(*, root: Path | None = None) -> dict[str, Any]:
    """Return compact region/title/exclusion context for agent-driven web search."""
    base = _root(root)
    config = _read_yaml(base / "config" / "job_hunter.yml")
    ljs = (config.get("search") or {}).get("llm_search") or {}
    scoring = config.get("scoring") or {}
    exclusions = config.get("exclusions") or {}
    return {
        "enabled": bool(ljs.get("enabled", False)),
        "trigger_threshold": int(ljs.get("trigger_threshold", 999)),
        "max_results_per_run": int(ljs.get("max_results_per_run", 20)),
        "batch_size": int(scoring.get("batch_size", DEFAULT_BATCH_SIZE)),
        "searches_per_title_per_region": 5,
        "regions": _llm_search_regions(config),
        "exclusions": {
            "excluded_companies": [str(company) for company in exclusions.get("companies", []) or []],
            "excluded_title_terms": [str(term) for term in exclusions.get("title_terms", []) or []],
            "excluded_url_patterns": [str(pattern) for pattern in EXCLUDED_LISTING_URL_PATTERNS],
            "excluded_languages": [str(language) for language in exclusions.get("languages", []) or []],
            "stale_indicators": [str(indicator) for indicator in STALE_INDICATORS],
        },
    }


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
