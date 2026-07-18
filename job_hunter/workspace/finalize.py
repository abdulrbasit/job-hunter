"""Deterministic finalize-run bookkeeping: discard dead job folders, validate durable run
artifacts, sync processed state, commit the finalize allowlist, and optionally push. Pure
— no typer, no printing — so it can be shared by `job-hunter finalize`, `internal
finalize-run`, and the dashboard Finalize button without ux/ ever importing cli/.
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from job_hunter.workspace.git_sync import FINALIZE_PATHS

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


def cleanup_transient_state(root: Path) -> list[str]:
    """Delete transient agent state files/dirs. Returns the relative paths removed."""
    cleaned: list[str] = []
    for rel in TRANSIENT_STATE_PATHS:
        p = root / rel
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            cleaned.append(rel)
    return cleaned


def sync_processed_from_job_outputs(root: Path) -> int:
    from job_hunter.tracking.repository import sync_from_job_folders

    return sync_from_job_folders(root)


def discard_job_folder(root: Path, job: str) -> bool:
    """Delete a job folder and mark its URL discarded. Returns False if the folder is missing."""
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


def _score_file_error(
    score_path: Path, meta: dict, job_dir: Path, policy: Any, validate_score_file: Callable[[Path], dict]
) -> str:
    import yaml

    try:
        raw_score = yaml.safe_load(score_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return f"{score_path.as_posix()}: invalid score.yml: {exc}"
    if str(raw_score.get("status") or "").lower() == "pending":
        return ""
    validation = validate_score_file(score_path)
    if not validation["valid"]:
        return f"{score_path.as_posix()}: invalid score.yml: {validation['error']}"
    if str(raw_score.get("decision") or "").upper() == "APPLY" and policy.is_excluded_company(
        str(meta.get("company") or "")
    ):
        return f"{job_dir.as_posix()}: APPLY job is from excluded company {meta.get('company')}"
    return ""


def _today_job_errors(root: Path, validate_score_file: Callable[[Path], dict]) -> list[str]:
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
        if error := _score_file_error(score_path, meta, job_dir, policy, validate_score_file):
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


def validate_run_artifacts(root: Path, validate_score_file: Callable[[Path], dict]) -> list[str]:
    """`validate_score_file` (job_hunter.agent_context.validate_score_file) is injected by
    the caller — workspace/ must not depend on agent_context/ (docs/architecture.md), and
    both current callers (cli/, ux/) are already exempt and may import it directly."""
    return [*_today_job_errors(root, validate_score_file), *_readme_link_errors(root)]


def stage_and_commit_finalize_paths(
    root: Path, finalize_paths: tuple[str, ...], message: str | None
) -> tuple[bool, str | None]:
    """Stage and commit the finalize allowlist. Returns (committed, message)."""
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *finalize_paths],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        raise RuntimeError(status.stderr.strip() or "git status failed")
    if not status.stdout.strip():
        return False, None

    if message is None:
        changed_paths = [line[3:] for line in status.stdout.splitlines() if line]
        message = derive_finalize_message(changed_paths)

    existing_paths = [path for path in finalize_paths if (root / path).exists()]
    subprocess.run(["git", "add", "--force", "--", *existing_paths], check=True, cwd=root)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False)
    if staged.returncode == 0:
        return False, None
    subprocess.run(["git", "commit", "-m", message], check=True, cwd=root)
    return True, message


def run_finalize_core(
    root: Path,
    *,
    verify_errors: list[str],
    validate_score_file: Callable[[Path], dict],
    message: str | None = None,
    push: bool = False,
    mode: str = "manual",
) -> dict[str, Any]:
    """Validate, commit, and optionally push durable run artifacts. Returns a result dict,
    never raises — the shared body behind `job-hunter finalize`, `internal finalize-run`,
    and the dashboard Finalize button.

    `verify_errors` (job_hunter.ux.health.verify_repository(root)["errors"]) and
    `validate_score_file` (job_hunter.agent_context.validate_score_file) are injected by
    the caller: workspace/ must not depend on ux/ or agent_context/ (docs/architecture.md),
    and both current callers (cli/, ux/ itself) are already exempt and may import them directly.
    """
    if verify_errors:
        return {"ok": False, "error": "; ".join(verify_errors[:20]), "stage": "verify"}

    discarded = discard_dead_job_folders(root)

    validation_errors = validate_run_artifacts(root, validate_score_file)
    if validation_errors:
        return {
            "ok": False,
            "error": "; ".join(validation_errors[:20]),
            "stage": "validation",
            "discarded": len(discarded),
        }

    synced = sync_processed_from_job_outputs(root)

    try:
        committed, commit_message = stage_and_commit_finalize_paths(root, FINALIZE_PATHS, message)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc), "stage": "commit", "discarded": len(discarded), "synced": synced}

    pushed = False
    merge_counts: dict[str, int] | None = None
    if committed and (push or mode == "auto"):
        from job_hunter.workspace.git_sync import merge_and_push

        push_result = merge_and_push(root)
        if not push_result["ok"]:
            return {
                "ok": False,
                "error": push_result["error"],
                "stage": "push",
                "discarded": len(discarded),
                "synced": synced,
                "committed": True,
                "message": commit_message,
            }
        pushed = True
        merge_counts = {k: push_result[k] for k in ("inserted", "updated", "deleted")}

    cleaned = cleanup_transient_state(root)

    result: dict[str, Any] = {
        "ok": True,
        "discarded": len(discarded),
        "synced": synced,
        "committed": committed,
        "message": commit_message,
        "pushed": pushed,
        "cleaned": cleaned,
    }
    if merge_counts is not None:
        result["merge"] = merge_counts
    return result
