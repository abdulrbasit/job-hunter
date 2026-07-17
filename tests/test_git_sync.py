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

    assert result == {"inserted": 1, "updated": 0, "deleted": 0}
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

    assert result == {"inserted": 0, "updated": 0, "deleted": 0}


# ---------------------------------------------------------------------------
# Tombstones — deleted jobs must never come back on sync
# ---------------------------------------------------------------------------


def test_merge_remote_jobs_handles_remote_snapshot_without_tombstone_table(tmp_path: Path) -> None:
    """Regression: a remote jobs.db written before the deleted_jobs table existed (any
    real workspace's pre-fix history) has no such table — merge must not crash on it,
    just treat it as having no tombstones."""
    import sqlite3

    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)
    old_remote_db = remote_root / "outputs" / "state" / "jobs.db"

    conn = sqlite3.connect(old_remote_db)
    conn.execute(
        """CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, canonical_url TEXT UNIQUE,
            slug TEXT UNIQUE, status TEXT DEFAULT 'candidate', title TEXT, company TEXT,
            notes TEXT DEFAULT '[]', created_at TEXT, updated_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO jobs (url, slug, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("https://old-schema.example/job", "old-job", "Engineer", "2026-01-01", "2026-01-01"),
    )
    conn.commit()
    conn.close()

    result = merge_remote_jobs(local_root, old_remote_db)

    assert result == {"inserted": 1, "updated": 0, "deleted": 0}
    assert get_job_by_slug(local_root, "old-job")["title"] == "Engineer"


def test_merge_remote_jobs_does_not_resurrect_locally_deleted_row(tmp_path: Path) -> None:
    """The exact bug reported: delete an application locally, sync — remote still has
    the older un-deleted row, and a naive merge re-inserts it as 'new'."""
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)

    from job_hunter.tracking.repository import delete_job

    upsert_job(local_root, {"url": "https://x.example/job", "slug": "job-1"})
    upsert_job(remote_root, {"url": "https://x.example/job", "slug": "job-1"})
    delete_job(local_root, "job-1")  # user deletes it locally, before syncing

    result = merge_remote_jobs(local_root, remote_root / "outputs" / "state" / "jobs.db")

    assert result == {"inserted": 0, "updated": 0, "deleted": 0}
    assert get_job_by_slug(local_root, "job-1") is None


def test_merge_remote_jobs_propagates_remote_deletion_to_local(tmp_path: Path) -> None:
    """Cross-machine case: another machine deleted the row and pushed its tombstone —
    this machine's own untouched copy must be removed too, not just left alone."""
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)

    from job_hunter.tracking.repository import delete_job

    upsert_job(local_root, {"url": "https://x.example/job", "slug": "job-1"})
    upsert_job(remote_root, {"url": "https://x.example/job", "slug": "job-1"})
    delete_job(remote_root, "job-1")  # deleted on the *other* machine

    result = merge_remote_jobs(local_root, remote_root / "outputs" / "state" / "jobs.db")

    assert result == {"inserted": 0, "updated": 0, "deleted": 1}
    assert get_job_by_slug(local_root, "job-1") is None


def test_merge_remote_jobs_tombstone_blocks_rediscovery_by_url_alone(tmp_path: Path) -> None:
    """A deleted job re-appearing on remote under the same URL but a fresh slug (e.g. a
    re-scrape) must still be blocked — tombstones match on url/canonical_url too, not
    just slug."""
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    (local_root / "outputs" / "state").mkdir(parents=True)
    (remote_root / "outputs" / "state").mkdir(parents=True)

    from job_hunter.tracking.repository import delete_job

    upsert_job(local_root, {"url": "https://x.example/job", "slug": "job-1"})
    delete_job(local_root, "job-1")
    upsert_job(remote_root, {"url": "https://x.example/job", "slug": "job-1"})

    result = merge_remote_jobs(local_root, remote_root / "outputs" / "state" / "jobs.db")

    assert result == {"inserted": 0, "updated": 0, "deleted": 0}
    assert get_job_by_slug(local_root, "job-1") is None


# ---------------------------------------------------------------------------
# git_sync orchestration (real git subprocess, bare-repo integration)
# ---------------------------------------------------------------------------


def test_sync_workspace_reports_error_without_remote(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".job-hunter").mkdir()
    (tmp_path / ".job-hunter" / "manifest.json").write_text("{}", encoding="utf-8")

    result = git_sync.sync_workspace(tmp_path)

    assert result["ok"] is False
    assert "remote" in result["error"].lower()


def test_sync_workspace_refuses_without_workspace_manifest(tmp_path: Path) -> None:
    """Regression: job-hunter dash launched from inside the job-hunter package's own
    source checkout (whose config/job_hunter.yml is a dev/test fixture, not a real
    workspace) once auto-committed and pushed the source tree's dirty build artifacts,
    because sync_workspace had no way to tell "real workspace" from "source checkout".
    .job-hunter/manifest.json (written only by `job-hunter init`) is the only reliable
    marker — its absence must hard-refuse before touching git at all, commit included."""
    _init_repo(tmp_path)
    _git(["remote", "add", "origin", "https://example.invalid/repo.git"], tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text("mode: agent\n", encoding="utf-8")
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-m", "initial"], tmp_path)
    (tmp_path / "README.md").write_text("dirty local edit\n", encoding="utf-8")

    result = git_sync.sync_workspace(tmp_path)

    assert result["ok"] is False
    assert "workspace" in result["error"].lower()
    status = _git(["status", "--porcelain"], tmp_path)
    assert "README.md" in status.stdout  # confirms nothing was staged/committed


def test_merge_and_push_refuses_without_workspace_manifest(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _git(["remote", "add", "origin", "https://example.invalid/repo.git"], tmp_path)

    result = git_sync.merge_and_push(tmp_path)

    assert result["ok"] is False
    assert "workspace" in result["error"].lower()


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
    (clone_a / ".job-hunter").mkdir()
    (clone_a / ".job-hunter" / "manifest.json").write_text("{}", encoding="utf-8")
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


def test_sync_workspace_deletion_survives_repeated_sync(_two_clones: tuple[Path, Path]) -> None:
    """End-to-end reproduction of the reported bug: delete an application, sync — it must
    stay gone, including on a second sync of the same machine and after another machine
    (which never saw the delete) syncs too."""
    clone_a, clone_b = _two_clones
    git_sync.sync_workspace(clone_b)  # b picks up the seed row first
    assert get_job_by_slug(clone_b, "seed") is not None

    from job_hunter.tracking.repository import delete_job

    delete_job(clone_a, "seed")
    result_a = git_sync.sync_workspace(clone_a)
    assert result_a["ok"] is True, result_a
    assert get_job_by_slug(clone_a, "seed") is None

    # Syncing the same machine again must not resurrect it from its own remote push.
    result_a_again = git_sync.sync_workspace(clone_a)
    assert result_a_again["ok"] is True, result_a_again
    assert get_job_by_slug(clone_a, "seed") is None

    # b never deleted it locally — its own sync must still remove it via the tombstone.
    result_b = git_sync.sync_workspace(clone_b)
    assert result_b["ok"] is True, result_b
    assert result_b["deleted"] == 1
    assert get_job_by_slug(clone_b, "seed") is None


def test_sync_status_reports_ahead_and_behind(_two_clones: tuple[Path, Path]) -> None:
    clone_a, clone_b = _two_clones

    upsert_job(clone_b, {"url": "https://b.example/y", "slug": "from-b"})
    _git(["add", "-A"], clone_b)
    _git(["commit", "-m", "from b"], clone_b)
    _git(["push", "origin", "HEAD:main"], clone_b)

    status = git_sync.sync_status(clone_a)

    assert status["ok"] is True
    assert status["behind"] >= 1
