"""Lossless git sync for a workspace: fetch, merge outputs/state/jobs.db, rebase, push.

jobs.db is a committed binary SQLite file, so a plain `git rebase` can't 3-way-merge it —
whichever side loses a conflict silently drops rows. sync_workspace merges the remote
snapshot into the local DB (tracking.repository.merge_remote_jobs) before rebasing, so a
rebase conflict on outputs/* can always be resolved by keeping the local side, which by
then is a superset of the remote's rows. Everything here shells out to git directly —
this is the same trust boundary as workspace/safety.py's git status calls.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Durable, git-tracked run artifacts — every path a `sync` commit or a `finalize-run`
# commit is allowed to stage. Canonical home for this list: cli/_run_artifacts.py's
# FINALIZE_PATHS re-exports it (cli/ may depend on workspace/, not the reverse).
FINALIZE_PATHS = (
    "README.md",
    "config",
    "profile",
    "outputs/jobs",
    "outputs/linkedin",
    "outputs/state/dev_token_metrics.json",
    "outputs/state/jobs.db",
)


def _run_git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)


def _current_branch(root: Path) -> str:
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "main"


def has_remote(root: Path) -> bool:
    result = _run_git(["remote"], root)
    return result.returncode == 0 and bool(result.stdout.strip())


def commit_dirty_paths(root: Path, paths: tuple[str, ...], message: str) -> bool:
    """Stage and commit any dirty files under `paths`. Returns True if a commit was made."""
    status = _run_git(["status", "--porcelain", "--untracked-files=all", "--", *paths], root)
    if status.returncode != 0 or not status.stdout.strip():
        return False
    existing_paths = [p for p in paths if (root / p).exists()]
    if not existing_paths:
        return False
    _run_git(["add", "--force", "--", *existing_paths], root)
    staged = _run_git(["diff", "--cached", "--quiet"], root)
    if staged.returncode == 0:
        return False
    commit = _run_git(["commit", "-m", message], root)
    return commit.returncode == 0


def _resolve_rebase_conflicts(root: Path) -> bool:
    """Resolve a rebase conflict: keep local for outputs/* (already a jobs.db superset
    after merge_remote_jobs), keep upstream everywhere else. Returns True if resolved."""
    conflicts = _run_git(["diff", "--name-only", "--diff-filter=U"], root)
    for path in conflicts.stdout.splitlines():
        path = path.strip()
        if not path:
            continue
        # During a rebase, "theirs" is the commit being replayed (local); "ours" is the
        # branch being rebased onto (upstream) — the reverse of normal merge semantics.
        side = "--theirs" if path.startswith("outputs/") else "--ours"
        _run_git(["checkout", side, "--", path], root)
    _run_git(["add", "-u"], root)
    result = _run_git(["rebase", "--continue"], root)
    return result.returncode == 0


def _rebase_onto(root: Path, branch: str) -> bool:
    result = _run_git(["rebase", f"origin/{branch}"], root)
    if result.returncode == 0:
        return True
    if _resolve_rebase_conflicts(root):
        return True
    _run_git(["rebase", "--abort"], root)
    return False


def _run_git_binary(args: list[str], root: Path) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else b""


def merge_and_push(root: Path) -> dict[str, Any]:
    """Fetch, merge the remote jobs.db into the local one, rebase, and push with retries.

    Assumes any local durable changes are already committed. Safe to call unattended —
    the DB merge means a rebase conflict on outputs/* is always auto-resolvable, so this
    never leaves the workspace mid-conflict.
    """
    if not has_remote(root):
        return {
            "ok": False,
            "error": "No git remote configured.",
            "next_action": "Connect this workspace to GitHub first — see Get Started.",
        }

    branch = _current_branch(root)
    fetch = _run_git(["fetch", "origin", branch], root)
    if fetch.returncode != 0:
        return {
            "ok": False,
            "error": fetch.stderr.strip() or "git fetch failed",
            "next_action": "Check your network connection and GitHub sign-in.",
        }

    from job_hunter.tracking.repository import merge_remote_jobs

    merged = {"inserted": 0, "updated": 0, "deleted": 0}
    snapshot_bytes = _run_git_binary(["show", f"origin/{branch}:outputs/state/jobs.db"], root)
    if snapshot_bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            remote_snapshot = Path(tmpdir) / "remote_jobs.db"
            remote_snapshot.write_bytes(snapshot_bytes)
            merged = merge_remote_jobs(root, remote_snapshot)
        if merged["inserted"] or merged["updated"] or merged["deleted"]:
            commit_dirty_paths(root, ("outputs/state/jobs.db",), "chore(sync): merge remote job state")

    if not _rebase_onto(root, branch):
        return {
            "ok": False,
            "error": "Rebase failed and could not be auto-resolved.",
            "next_action": "Open the workspace in a terminal and run `git status` to resolve manually.",
        }

    for _ in range(3):
        push = _run_git(["push", "origin", f"HEAD:{branch}"], root)
        if push.returncode == 0:
            return {
                "ok": True,
                "inserted": merged["inserted"],
                "updated": merged["updated"],
                "deleted": merged["deleted"],
                "pushed": True,
            }
        _run_git(["fetch", "origin", branch], root)
        if not _rebase_onto(root, branch):
            break

    return {
        "ok": False,
        "error": "Push failed after retries.",
        "next_action": "Try again, or open a terminal and run `git push`.",
    }


def sync_workspace(root: Path, *, message: str = "chore(sync): local changes") -> dict[str, Any]:
    """Commit dirty durable state, then merge_and_push. The one-call entry point for the GUI."""
    commit_dirty_paths(root, FINALIZE_PATHS, message)
    return merge_and_push(root)


def sync_status(root: Path) -> dict[str, Any]:
    """Ahead/behind counts vs the upstream branch, after a fetch. Never raises."""
    if not has_remote(root):
        return {"ok": False, "error": "No git remote configured."}
    branch = _current_branch(root)
    fetch = _run_git(["fetch", "origin", branch], root)
    if fetch.returncode != 0:
        return {"ok": False, "error": fetch.stderr.strip() or "git fetch failed"}
    counts = _run_git(["rev-list", "--left-right", "--count", f"origin/{branch}...HEAD"], root)
    if counts.returncode != 0:
        return {"ok": False, "error": counts.stderr.strip() or "git rev-list failed"}
    behind_text, ahead_text = counts.stdout.split()
    return {"ok": True, "ahead": int(ahead_text), "behind": int(behind_text)}
