"""Tests for job_hunter.metrics.store."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_hunter.metrics.store import get_runs, init_db, record_run


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    p = tmp_path / "metrics.db"
    init_db(p)
    return p


def test_init_creates_db(db: Path) -> None:
    assert db.exists()


def test_record_and_get(db: Path) -> None:
    record_run(
        db,
        ts="2026-06-28T12:00:00+00:00",
        mode="hunt",
        exec_mode="llm-api",
        region="DE",
        duration_s=42.5,
        jobs_found=15,
        jobs_tailored=3,
        token_totals={"scoring": {"in": 1000, "out": 200, "cached": 50}},
        total_cost_usd=0.012,
        scrape_stats={},
    )
    runs = get_runs(db)
    assert len(runs) == 1
    r = runs[0]
    assert r["mode"] == "hunt"
    assert r["exec_mode"] == "llm-api"
    assert r["region"] == "DE"
    assert r["jobs_found"] == 15
    assert r["jobs_tailored"] == 3
    assert r["duration_s"] == pytest.approx(42.5)
    assert r["total_cost_usd"] == pytest.approx(0.012)
    assert r["token_totals"]["scoring"]["in"] == 1000


def test_get_runs_limit(db: Path) -> None:
    for i in range(5):
        record_run(
            db,
            ts=f"2026-06-{i + 1:02d}T00:00:00+00:00",
            mode="hunt",
            exec_mode="llm-api",
            region="",
            duration_s=1.0,
            jobs_found=i,
            jobs_tailored=0,
            token_totals={},
            total_cost_usd=None,
            scrape_stats={},
        )
    assert len(get_runs(db, limit=3)) == 3


def test_get_runs_empty(tmp_path: Path) -> None:
    assert get_runs(tmp_path / "nonexistent.db") == []


def test_get_runs_ordering(db: Path) -> None:
    record_run(
        db,
        ts="2026-06-01T00:00:00+00:00",
        mode="hunt",
        exec_mode="llm-api",
        region="",
        duration_s=1.0,
        jobs_found=1,
        jobs_tailored=0,
        token_totals={},
        total_cost_usd=None,
        scrape_stats={},
    )
    record_run(
        db,
        ts="2026-06-28T00:00:00+00:00",
        mode="hunt",
        exec_mode="llm-api",
        region="",
        duration_s=1.0,
        jobs_found=2,
        jobs_tailored=0,
        token_totals={},
        total_cost_usd=None,
        scrape_stats={},
    )
    runs = get_runs(db)
    assert runs[0]["jobs_found"] == 2  # most recent first
