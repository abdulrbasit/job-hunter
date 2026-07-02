from __future__ import annotations

import sqlite3
from pathlib import Path

from job_hunter.tracking import repository


def test_connection_uses_delete_journal_and_busy_timeout(tmp_path: Path) -> None:
    with repository._conn(tmp_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10_000


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
