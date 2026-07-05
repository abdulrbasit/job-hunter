"""Company-hunt run/task persistence — additive tables in the same jobs.db.

Precreating pending tasks before work starts, and persisting each task's result the
moment it finishes, is what makes a crash mid-run resumable: the next mode="resume"
invocation picks up exactly the tasks still 'pending' instead of restarting from zero.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_hunter.tracking.repository import db_path

_DDL = """
CREATE TABLE IF NOT EXISTS company_hunt_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    mode          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'running',
    total         INTEGER NOT NULL DEFAULT 0,
    succeeded     INTEGER NOT NULL DEFAULT 0,
    failed        INTEGER NOT NULL DEFAULT 0,
    skipped       INTEGER NOT NULL DEFAULT 0,
    jobs_observed INTEGER NOT NULL DEFAULT 0,
    jobs_inserted INTEGER NOT NULL DEFAULT 0,
    error         TEXT NOT NULL DEFAULT '',
    started_at    TEXT NOT NULL,
    finished_at   TEXT
);

CREATE TABLE IF NOT EXISTS company_hunt_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER NOT NULL,
    company_name      TEXT NOT NULL DEFAULT '',
    career_url        TEXT NOT NULL DEFAULT '',
    location          TEXT NOT NULL DEFAULT '',
    enabled           INTEGER NOT NULL DEFAULT 1,
    status            TEXT NOT NULL DEFAULT 'pending',
    extraction_method TEXT NOT NULL DEFAULT '',
    duration_s        REAL,
    jobs_observed     INTEGER NOT NULL DEFAULT 0,
    jobs_inserted     INTEGER NOT NULL DEFAULT 0,
    failure_reason    TEXT NOT NULL DEFAULT '',
    etag              TEXT NOT NULL DEFAULT '',
    last_modified     TEXT NOT NULL DEFAULT '',
    fingerprint       TEXT NOT NULL DEFAULT '',
    started_at        TEXT,
    finished_at       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_company_hunt_tasks_run_id ON company_hunt_tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_company_hunt_tasks_career_url ON company_hunt_tasks(career_url);

CREATE TABLE IF NOT EXISTS company_hunt_updates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL,
    task_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_company_hunt_updates_run_id ON company_hunt_updates(run_id, id);
"""

PENDING = "pending"
RUNNING = "running"
OK = "ok"
FAILED = "failed"
SKIPPED = "skipped"

MODE_NEW_CHANGED = "new_changed"
MODE_FAILED_ONLY = "failed_only"
MODE_FORCE_ALL = "force_all"
MODE_RESUME = "resume"

DEFAULT_COOLDOWN_HOURS = 24


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _conn(root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(root), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    return conn


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def begin_run(root: Path, mode: str) -> int:
    now = _now()
    with _conn(root) as conn:
        cursor = conn.execute(
            "INSERT INTO company_hunt_runs (mode, status, started_at) VALUES (?, 'running', ?)",
            (mode, now),
        )
        return int(cursor.lastrowid)


def create_tasks(root: Path, run_id: int, companies: list[Any], status: str) -> None:
    """Precreate task rows for companies in this run, at the given initial status.

    status='pending' for companies about to be processed this run; status='skipped'
    for companies this run's mode is choosing not to re-hunt (still visible, just
    not re-fetched) — either way they count toward the run's total up front.
    """
    if not companies:
        return
    now = _now()
    rows = [
        (
            run_id,
            str(c.get("name") or "") if isinstance(c, dict) else str(c),
            str(c.get("career_url") or "") if isinstance(c, dict) else "",
            str(c.get("location") or "") if isinstance(c, dict) else "",
            0 if (isinstance(c, dict) and c.get("enabled") is False) else 1,
            status,
            now,
            now,
        )
        for c in companies
    ]
    with _conn(root) as conn:
        for row in rows:
            cursor = conn.execute(
                """INSERT INTO company_hunt_tasks
                   (run_id, company_name, career_url, location, enabled, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )
            if status == SKIPPED:
                conn.execute(
                    "INSERT INTO company_hunt_updates (run_id, task_id, created_at) VALUES (?, ?, ?)",
                    (run_id, int(cursor.lastrowid), now),
                )
        conn.execute("UPDATE company_hunt_runs SET total = total + ? WHERE id = ?", (len(rows), run_id))
        if status == SKIPPED:
            conn.execute("UPDATE company_hunt_runs SET skipped = skipped + ? WHERE id = ?", (len(rows), run_id))


def get_tasks_for_run(root: Path, run_id: int) -> list[dict[str, Any]]:
    with _conn(root) as conn:
        rows = conn.execute("SELECT * FROM company_hunt_tasks WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    return [dict(row) for row in rows]


def get_pending_tasks(root: Path, run_id: int) -> list[dict[str, Any]]:
    with _conn(root) as conn:
        rows = conn.execute(
            "SELECT * FROM company_hunt_tasks WHERE run_id = ? AND status = ? ORDER BY id", (run_id, PENDING)
        ).fetchall()
    return [dict(row) for row in rows]


def prepare_resume(root: Path, run_id: int) -> None:
    """Requeue work that was in-flight when the previous process stopped."""
    now = _now()
    with _conn(root) as conn:
        conn.execute(
            """UPDATE company_hunt_tasks
               SET status = ?, started_at = NULL, updated_at = ?
               WHERE run_id = ? AND status = ?""",
            (PENDING, now, run_id, RUNNING),
        )


def start_task(root: Path, task_id: int) -> None:
    now = _now()
    with _conn(root) as conn:
        conn.execute(
            "UPDATE company_hunt_tasks SET status=?, started_at=?, updated_at=? WHERE id=?",
            (RUNNING, now, now, task_id),
        )


def finish_task(
    root: Path,
    task_id: int,
    run_id: int,
    *,
    status: str,
    extraction_method: str = "",
    duration_s: float | None = None,
    jobs_observed: int = 0,
    jobs_inserted: int = 0,
    failure_reason: str = "",
    etag: str = "",
    last_modified: str = "",
    fingerprint: str = "",
) -> None:
    now = _now()
    with _conn(root) as conn:
        cursor = conn.execute(
            """UPDATE company_hunt_tasks SET
                status=?, extraction_method=?, duration_s=?, jobs_observed=?, jobs_inserted=?,
                failure_reason=?, etag=?, last_modified=?, fingerprint=?, finished_at=?, updated_at=?
               WHERE id=? AND run_id=? AND status IN (?, ?)""",
            (
                status,
                extraction_method,
                duration_s,
                jobs_observed,
                jobs_inserted,
                failure_reason,
                etag,
                last_modified,
                fingerprint,
                now,
                now,
                task_id,
                run_id,
                PENDING,
                RUNNING,
            ),
        )
        if cursor.rowcount == 0:
            return
        conn.execute(
            """UPDATE company_hunt_runs SET
                succeeded = succeeded + ?, failed = failed + ?,
                jobs_observed = jobs_observed + ?, jobs_inserted = jobs_inserted + ?
               WHERE id = ?""",
            (1 if status == OK else 0, 1 if status == FAILED else 0, jobs_observed, jobs_inserted, run_id),
        )
        conn.execute(
            "INSERT INTO company_hunt_updates (run_id, task_id, created_at) VALUES (?, ?, ?)",
            (run_id, task_id, now),
        )


def finish_run(root: Path, run_id: int, *, status: str = "done", error: str = "") -> None:
    now = _now()
    with _conn(root) as conn:
        conn.execute(
            "UPDATE company_hunt_runs SET status=?, error=?, finished_at=? WHERE id=?",
            (status, error, now, run_id),
        )


def get_run(root: Path, run_id: int) -> dict[str, Any] | None:
    with _conn(root) as conn:
        row = conn.execute("SELECT * FROM company_hunt_runs WHERE id = ?", (run_id,)).fetchone()
    return _row(row)


def get_latest_run(root: Path) -> dict[str, Any] | None:
    with _conn(root) as conn:
        row = conn.execute("SELECT * FROM company_hunt_runs ORDER BY id DESC LIMIT 1").fetchone()
    return _row(row)


def find_resumable_run(root: Path) -> dict[str, Any] | None:
    """Most recent run still in status='running' — implies an interrupted process."""
    with _conn(root) as conn:
        row = conn.execute(
            "SELECT * FROM company_hunt_runs WHERE status = ? ORDER BY id DESC LIMIT 1", (RUNNING,)
        ).fetchone()
    return _row(row)


def get_last_task_for_url(root: Path, career_url: str) -> dict[str, Any] | None:
    """Most recent terminal (ok/failed) task for this career_url, across all runs."""
    if not career_url:
        return None
    with _conn(root) as conn:
        row = conn.execute(
            """SELECT * FROM company_hunt_tasks
               WHERE career_url = ? AND status IN (?, ?)
               ORDER BY id DESC LIMIT 1""",
            (career_url, OK, FAILED),
        ).fetchone()
    return _row(row)


def get_latest_task_by_url(root: Path) -> dict[str, dict[str, Any]]:
    """Latest terminal task per career_url — backs the Companies UI's 'latest status' column."""
    with _conn(root) as conn:
        rows = conn.execute(
            """SELECT t.* FROM company_hunt_tasks t
               INNER JOIN (
                   SELECT career_url, MAX(id) AS max_id FROM company_hunt_tasks
                   WHERE status IN (?, ?) GROUP BY career_url
               ) latest ON t.career_url = latest.career_url AND t.id = latest.max_id""",
            (OK, FAILED),
        ).fetchall()
    return {row["career_url"]: dict(row) for row in rows}


def get_updates_since(root: Path, run_id: int, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    """Return terminal task updates after an append-only completion cursor."""
    with _conn(root) as conn:
        rows = conn.execute(
            """SELECT t.*, u.id AS update_id
               FROM company_hunt_updates u
               JOIN company_hunt_tasks t ON t.id = u.task_id
               WHERE u.run_id = ? AND u.id > ?
               ORDER BY u.id LIMIT ?""",
            (run_id, after_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
