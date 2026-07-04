from __future__ import annotations

import sqlite3
from pathlib import Path

from job_hunter.tracking import repository


def test_connection_uses_delete_journal_and_busy_timeout(tmp_path: Path) -> None:
    with repository._conn(tmp_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10_000


def test_insert_jobs_merges_canonical_url_collision_instead_of_crashing(tmp_path: Path) -> None:
    """Two raw URLs that canonicalize to the same value must not raise IntegrityError."""
    inserted = repository.insert_jobs(
        tmp_path,
        [
            {"url": "https://example.com/job/123?utm_source=a", "title": "Engineer", "company": "Acme"},
            {"url": "https://example.com/job/123?utm_source=b", "title": "Engineer", "company": "Acme"},
        ],
    )

    assert inserted == 2  # caller-facing count of jobs processed, not new rows
    jobs = repository.get_discovered_jobs(tmp_path)
    assert len(jobs) == 1
    assert jobs[0]["canonical_url"] == "https://example.com/job/123"


def test_mark_candidates_discarded_sets_status_and_reason(tmp_path: Path) -> None:
    repository.insert_jobs(tmp_path, [{"url": "https://example.com/job/1", "title": "PM", "company": "Acme"}])

    marked = repository.mark_candidates_discarded(
        tmp_path, [{"url": "https://example.com/job/1", "reason": "hard_screen_skip, wrong_location"}]
    )

    assert marked == 1
    job = repository.get_job_by_url(tmp_path, "https://example.com/job/1")
    assert job is not None
    assert job["status"] == "discarded"
    assert job["notes"] == ["hard_screen_skip, wrong_location"]


def test_mark_candidates_discarded_never_clobbers_advanced_job(tmp_path: Path) -> None:
    """A job already past the candidate stage (e.g. tailored) must not be reverted to discarded."""
    repository.upsert_job(tmp_path, {"url": "https://example.com/job/2", "slug": "acme-pm", "status": "tailored"})

    marked = repository.mark_candidates_discarded(
        tmp_path, [{"url": "https://example.com/job/2", "reason": "screen_skip"}]
    )

    assert marked == 0
    job = repository.get_job_by_slug(tmp_path, "acme-pm")
    assert job is not None
    assert job["status"] == "tailored"


def test_existing_wal_database_migrates_without_sidecars(tmp_path: Path) -> None:
    db = tmp_path / "outputs" / "state" / "jobs.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE legacy (id INTEGER)")
        conn.execute("INSERT INTO legacy VALUES (1)")
        conn.commit()
    finally:
        conn.close()

    repository.get_jobs(tmp_path)

    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert not Path(f"{db}-wal").exists()
    assert not Path(f"{db}-shm").exists()
