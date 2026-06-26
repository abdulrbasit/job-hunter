"""Helpers for durable and transient run artifacts used by CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

FINALIZE_PATHS = (
    "README.md",
    "config",
    "profile",
    "outputs/applications.yml",
    "outputs/candidates",
    "outputs/jobs",
    "outputs/linkedin",
    "outputs/state/api_usage.json",
    "outputs/state/dev_token_metrics.json",
    "outputs/state/discovered_urls.yml",
)
TRANSIENT_STATE_PATHS = (
    "outputs/state/agent_candidate_queue.json",
    "outputs/state/agent_candidate_batch.json",
    "outputs/state/batch_scores.yml",
    "outputs/state/batch_screen.yml",
    "outputs/state/batch_judgment.yml",
)


def cleanup_transient_state(root: Path, *, label: str) -> int:
    cleaned = 0
    for rel in TRANSIENT_STATE_PATHS:
        p = root / rel
        if p.exists():
            p.unlink()
            cleaned += 1
            typer.echo(f"[{label}] cleaned up {rel}")
    return cleaned


def sync_processed_from_job_outputs(root: Path) -> int:
    import yaml

    jobs_dir = root / "outputs" / "jobs"
    if not jobs_dir.exists():
        return 0

    state_path = root / "outputs" / "state" / "discovered_urls.yml"
    if state_path.exists():
        state = yaml.safe_load(state_path.read_text(encoding="utf-8")) or {}
    else:
        state = {}
    urls = set(state.get("discovered", []) or [])
    before = len(urls)

    for meta_path in sorted(jobs_dir.glob("*/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        url = str(meta.get("url") or "")
        if url:
            urls.add(url)

    added = len(urls) - before
    if not added:
        return 0

    state_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# URL-only dedup state. Each entry is a canonical job URL.\n"
        "# Automatically updated after each run.\n"
        "# Remove a URL manually to rediscover or reprocess that job.\n\n"
    )
    state_path.write_text(
        header + yaml.safe_dump({"discovered": sorted(urls)}, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return added


def _score_file_error(score_path: Path, meta: dict, job_dir: Path, policy: Any) -> str:
    import yaml

    from job_hunter import agent_context

    try:
        raw_score = yaml.safe_load(score_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return f"{score_path.as_posix()}: invalid score.yml: {exc}"
    if str(raw_score.get("status") or "").lower() == "pending":
        return ""
    validation = agent_context.validate_score_file(score_path)
    if not validation["valid"]:
        return f"{score_path.as_posix()}: invalid score.yml: {validation['error']}"
    if str(raw_score.get("decision") or "").upper() == "APPLY" and policy.is_excluded_company(
        str(meta.get("company") or "")
    ):
        return f"{job_dir.as_posix()}: APPLY job is from excluded company {meta.get('company')}"
    return ""


def _today_job_errors(root: Path) -> list[str]:
    from datetime import date

    import yaml

    from job_hunter.sources._policy import JobPolicy

    job_hunter_config = yaml.safe_load((root / "config" / "job_hunter.yml").read_text(encoding="utf-8")) or {}
    policy = JobPolicy(job_hunter_config)
    seen_application_keys: dict[str, str] = {}
    today = date.today().isoformat()
    errors: list[str] = []

    for job_dir in sorted((root / "outputs" / "jobs").glob("*")):
        if not job_dir.is_dir():
            continue
        meta_path = job_dir / "meta.json"
        score_path = job_dir / "score.yml"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{meta_path.as_posix()}: invalid meta.json: {exc}")
            continue
        if not (job_dir.name.startswith(today) or meta.get("date") == today):
            continue
        key = f"{meta.get('company', '').lower()}::{meta.get('title', '').lower()}"
        if key != "::" and key in seen_application_keys:
            errors.append(f"{job_dir.as_posix()}: duplicate application title also in {seen_application_keys[key]}")
        elif key != "::":
            seen_application_keys[key] = job_dir.as_posix()

        if not score_path.exists():
            continue
        if error := _score_file_error(score_path, meta, job_dir, policy):
            errors.append(error)
    return errors


def _readme_link_errors(root: Path) -> list[str]:
    import re

    readme_path = root / "README.md"
    if not readme_path.exists():
        return []
    readme = readme_path.read_text(encoding="utf-8", errors="replace")
    return [
        f"README.md: broken Files link {rel}"
        for rel in re.findall(r"\[Files\]\((outputs/jobs/[^)]+/)\)", readme)
        if not (root / rel).exists()
    ]


def validate_run_artifacts(root: Path) -> list[str]:
    return [*_today_job_errors(root), *_readme_link_errors(root)]


def expand_listing_candidate(url: str, company: str, location: str, title: str) -> dict | None:
    from job_hunter.config import get_config
    from job_hunter.sources.search_providers import fetch_playwright_career_jobs

    search_cfg = get_config("job_hunter")
    title_filters = search_cfg.get("job_titles", [])
    excluded_terms = (search_cfg.get("exclusions", {}) or {}).get("title_terms", [])
    try:
        jobs = fetch_playwright_career_jobs(
            {"name": company or "Unknown Company", "career_url": url, "location": location},
            title_filters,
            excluded_terms,
        )
    except Exception:
        return None
    if not jobs:
        return None
    wanted = title.lower().strip()
    for job in jobs:
        found = str(job.get("title") or "").lower()
        if wanted and (wanted in found or found in wanted):
            return job
    return jobs[0] if len(jobs) == 1 else None
