"""Tests for job_hunter/workspace/git_sync.py and tracking.repository.merge_remote_jobs.

jobs.db is a committed binary SQLite file, so a plain git rebase can't 3-way-merge it.
merge_remote_jobs folds a remote snapshot into the local DB row-by-row so a rebase
conflict on outputs/* is always auto-resolvable by keeping the local side.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from job_hunter.tracking.repository import get_job_by_slug, merge_remote_jobs, upsert_job
from job_hunter.workspace import git_sync


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)


def _init_repo(root: Path) -> None:
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)


# ---------------------------------------------------------------------------
# merge_remote_jobs
# ---------------------------------------------------------------------------


def test_merge_remote_jobs_inserts_remote_only_row(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)

    upsert_job(remote_root, {"url": "https://x.example/job", "slug": "remote-job", "title": "Engineer"})

    result = merge_remote_jobs(local_root, remote_root / "outputs" / "state" / "jobs.db")

    assert result == {"inserted": 1, "updated": 0}
    assert get_job_by_slug(local_root, "remote-job")["title"] == "Engineer"


def test_merge_remote_jobs_promotes_status_forward_only(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)

    upsert_job(local_root, {"url": "https://x.example/job", "slug": "job-1", "status": "applied"})
    upsert_job(remote_root, {"url": "https://x.example/job", "slug": "job-1", "status": "candidate"})

    merge_remote_jobs(local_root, remote_root / "outputs" / "state" / "jobs.db")

    assert get_job_by_slug(local_root, "job-1")["status"] == "applied"


def test_merge_remote_jobs_adopts_remote_status_when_ahead(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)

    upsert_job(local_root, {"url": "https://x.example/job", "slug": "job-1", "status": "candidate"})
    upsert_job(remote_root, {"url": "https://x.example/job", "slug": "job-1", "status": "tailored"})

    merge_remote_jobs(local_root, remote_root / "outputs" / "state" / "jobs.db")

    assert get_job_by_slug(local_root, "job-1")["status"] == "tailored"


def test_merge_remote_jobs_unions_notes(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)

    upsert_job(local_root, {"url": "https://x.example/job", "slug": "job-1", "notes": ["local note"]})
    upsert_job(remote_root, {"url": "https://x.example/job", "slug": "job-1", "notes": ["remote note"]})

    merge_remote_jobs(local_root, remote_root / "outputs" / "state" / "jobs.db")

    assert set(get_job_by_slug(local_root, "job-1")["notes"]) == {"local note", "remote note"}


def test_merge_remote_jobs_fills_gaps_without_clobbering_local_values(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)

    upsert_job(local_root, {"url": "https://x.example/job", "slug": "job-1", "title": "Local Title"})
    upsert_job(
        remote_root,
        {"url": "https://x.example/job", "slug": "job-1", "title": "Remote Title", "company": "Remote Co"},
    )

    merge_remote_jobs(local_root, remote_root / "outputs" / "state" / "jobs.db")

    merged = get_job_by_slug(local_root, "job-1")
    assert merged["title"] == "Local Title"  # local non-empty value wins
    assert merged["company"] == "Remote Co"  # gap filled from remote


def test_merge_remote_jobs_empty_remote_db_is_noop(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)
    upsert_job(remote_root, {"url": "https://never.example/x", "slug": "z"})
    from job_hunter.tracking.repository import delete_job

    delete_job(remote_root, "z")

    result = merge_remote_jobs(local_root, remote_root / "outputs" / "state" / "jobs.db")

    assert result == {"inserted": 0, "updated": 0}


# ---------------------------------------------------------------------------
# git_sync orchestration (real git subprocess, bare-repo integration)
# ---------------------------------------------------------------------------


def test_sync_workspace_reports_error_without_remote(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    result = git_sync.sync_workspace(tmp_path)

    assert result["ok"] is False
    assert "remote" in result["error"].lower()


def test_sync_status_reports_error_without_remote(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    result = git_sync.sync_status(tmp_path)

    assert result["ok"] is False


@pytest.fixture
def _two_clones(tmp_path: Path) -> tuple[Path, Path]:
    """A bare 'origin' plus two working clones (simulating a laptop and a CI bot)."""
    bare = tmp_path / "origin.git"
    _git(["init", "--bare", "--initial-branch=main", str(bare)], tmp_path)

    clone_a = tmp_path / "clone_a"
    clone_b = tmp_path / "clone_b"
    _git(["clone", str(bare), str(clone_a)], tmp_path)
    _init_repo(clone_a)
    (clone_a / "README.md").write_text("hello\n", encoding="utf-8")
    (clone_a / "outputs" / "state").mkdir(parents=True)
    upsert_job(clone_a, {"url": "https://seed.example/x", "slug": "seed"})
    _git(["add", "-A"], clone_a)
    _git(["commit", "-m", "seed"], clone_a)
    _git(["push", "origin", "HEAD:main"], clone_a)

    _git(["clone", str(bare), str(clone_b)], tmp_path)
    _init_repo(clone_b)

    return clone_a, clone_b


def test_sync_workspace_merges_diverged_jobs_db_without_conflict(_two_clones: tuple[Path, Path]) -> None:
    clone_a, clone_b = _two_clones

    upsert_job(clone_a, {"url": "https://a.example/x", "slug": "from-a", "title": "From A"})
    result_a = git_sync.sync_workspace(clone_a)
    assert result_a["ok"] is True, result_a

    upsert_job(clone_b, {"url": "https://b.example/y", "slug": "from-b", "title": "From B"})
    result_b = git_sync.sync_workspace(clone_b)
    assert result_b["ok"] is True, result_b

    assert get_job_by_slug(clone_b, "from-a") is not None
    assert get_job_by_slug(clone_b, "seed") is not None

    result_a_again = git_sync.sync_workspace(clone_a)
    assert result_a_again["ok"] is True, result_a_again
    assert get_job_by_slug(clone_a, "from-b") is not None


def test_sync_workspace_preserves_local_status_promotion_across_machines(_two_clones: tuple[Path, Path]) -> None:
    clone_a, clone_b = _two_clones
    git_sync.sync_workspace(clone_b)  # b picks up the seed row first

    from job_hunter.tracking.repository import update_job_status

    update_job_status(clone_b, "seed", "applied")
    result_b = git_sync.sync_workspace(clone_b)
    assert result_b["ok"] is True, result_b

    result_a = git_sync.sync_workspace(clone_a)
    assert result_a["ok"] is True, result_a
    assert get_job_by_slug(clone_a, "seed")["status"] == "applied"


def test_sync_status_reports_ahead_and_behind(_two_clones: tuple[Path, Path]) -> None:
    clone_a, clone_b = _two_clones

    upsert_job(clone_b, {"url": "https://b.example/y", "slug": "from-b"})
    _git(["add", "-A"], clone_b)
    _git(["commit", "-m", "from b"], clone_b)
    _git(["push", "origin", "HEAD:main"], clone_b)

    status = git_sync.sync_status(clone_a)

    assert status["ok"] is True
    assert status["behind"] >= 1
