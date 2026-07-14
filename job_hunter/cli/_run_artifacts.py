"""Helpers for durable and transient run artifacts used by CLI commands."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import typer

from job_hunter.workspace.git_sync import FINALIZE_PATHS  # noqa: F401 — re-exported for cli/commands/internal.py

TRANSIENT_STATE_PATHS = (
    "outputs/state/agent_candidate_queue.json",
    "outputs/state/agent_candidate_batch.json",
    "outputs/state/batch_scores.yml",
    "outputs/state/batch_screen.yml",
    "outputs/state/batch_judgment.yml",
    "outputs/state/compiled",
)


def derive_finalize_message(changed_paths: list[str]) -> str:
    """Derive a finalize commit message from durable changed paths, applying the same
    precedence the finalize skill used to apply by reading a markdown table by hand."""
    today = datetime.date.today().isoformat()
    job_slugs = {p.split("/")[2] for p in changed_paths if p.startswith("outputs/jobs/") and len(p.split("/")) > 2}
    other_paths = [p for p in changed_paths if not p.startswith("outputs/jobs/")]

    if job_slugs:
        if len(job_slugs) == 1:
            return f"feat(jobs): tailor {next(iter(job_slugs))}"
        return f"feat(jobs): tailor batch {today}"
    if other_paths == ["profile/story_bank.md"]:
        return "feat(stories): update story bank"
    if other_paths and all(p.startswith("outputs/linkedin/") for p in other_paths):
        return f"feat(linkedin): add drafts {today}"
    if other_paths and all(p.startswith("config/") for p in other_paths):
        return "chore(config): update search config"
    if other_paths and all(p.startswith("profile/") for p in other_paths):
        return "chore(setup): update profile"
    if other_paths == ["README.md"]:
        return "chore(docs): update README"
    return f"chore: update {today}"


def cleanup_transient_state(root: Path, *, label: str) -> int:
    import shutil

    cleaned = 0
    for rel in TRANSIENT_STATE_PATHS:
        p = root / rel
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            cleaned += 1
            typer.echo(f"[{label}] cleaned up {rel}")
    return cleaned


def sync_processed_from_job_outputs(root: Path) -> int:
    from job_hunter.tracking.repository import sync_from_job_folders

    return sync_from_job_folders(root)


def discard_job_folder(root: Path, job: str) -> bool:
    """Delete a job folder and mark its URL discarded. Returns False if the folder is missing."""
    import shutil

    from job_hunter.tracking.processed_urls import load_processed, mark_processed

    folder = root / "outputs" / "jobs" / job
    if not folder.exists():
        return False
    meta_path = folder / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        mark_processed([meta], load_processed())
    shutil.rmtree(folder)
    return True


def discard_dead_job_folders(root: Path) -> list[str]:
    """Discard every SKIP-decisioned or missing-JD job folder before a finalize commit.

    Safety net for the same failure mode fixed earlier for candidate screening: an agent
    step that was supposed to discard a job can be skipped, leaving a dead folder that
    `finalize-run` would otherwise force-add into the commit.
    """
    import yaml

    jobs_dir = root / "outputs" / "jobs"
    if not jobs_dir.exists():
        return []

    discarded: list[str] = []
    for job_dir in sorted(jobs_dir.iterdir()):
        if not job_dir.is_dir():
            continue
        score_path = job_dir / "score.yml"
        meta_path = job_dir / "meta.json"
        is_skip = False
        is_missing_jd = False
        if score_path.exists():
            try:
                score = yaml.safe_load(score_path.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, UnicodeDecodeError):
                score = {}
            is_skip = str(score.get("decision") or "").upper() == "SKIP"
        elif meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                meta = {}
            is_missing_jd = str(meta.get("job_description_fetch_status") or "") == "fetch_failed"
        if (is_skip or is_missing_jd) and discard_job_folder(root, job_dir.name):
            discarded.append(job_dir.name)
    return discarded


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

    from job_hunter.sources.policy import JobPolicy

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
    from job_hunter.sources.search import fetch_playwright_career_jobs

    search_config = get_config("job_hunter")
    title_filters = search_config.get("job_titles", [])
    excluded_terms = (search_config.get("exclusions", {}) or {}).get("title_terms", [])
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
