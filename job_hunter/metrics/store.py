"""SQLite-backed metrics store for pipeline run history and token usage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    mode           TEXT,
    exec_mode      TEXT,
    region         TEXT,
    duration_s     REAL,
    jobs_found     INTEGER DEFAULT 0,
    jobs_tailored  INTEGER DEFAULT 0,
    token_totals   TEXT,
    total_cost_usd REAL,
    scrape_stats   TEXT
)
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(_DDL)


def record_run(
    db_path: Path,
    *,
    ts: str,
    mode: str,
    exec_mode: str,
    region: str,
    duration_s: float,
    jobs_found: int,
    jobs_tailored: int,
    token_totals: dict[str, Any],
    total_cost_usd: float | None,
    scrape_stats: dict[str, Any],
) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO pipeline_runs
               (ts, mode, exec_mode, region, duration_s, jobs_found, jobs_tailored,
                token_totals, total_cost_usd, scrape_stats)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                ts,
                mode,
                exec_mode,
                region,
                duration_s,
                jobs_found,
                jobs_tailored,
                json.dumps(token_totals),
                total_cost_usd,
                json.dumps(scrape_stats),
            ),
        )


def get_runs(db_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM pipeline_runs ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        for key in ("token_totals", "scrape_stats"):
            try:
                d[key] = json.loads(d[key]) if d.get(key) else {}
            except (json.JSONDecodeError, TypeError):
                d[key] = {}
        result.append(d)
    return result
