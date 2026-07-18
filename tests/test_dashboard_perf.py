"""Phase 4/4 optimize — dashboard backend latency on a 10k-job database.

Seeds a realistic 10k-row jobs.db (spread across every pipeline status, scored and
unscored, with rejection reasons and discovery dates) using the same insert_jobs-loop +
raw-UPDATE idiom as the existing 5000-row pagination test, then times the RPCs each
redesigned view calls on load. Ceilings are generous (seconds, not milliseconds) — this
guards against a query regression (e.g. an accidental N+1 or a dropped index), not a
tight benchmark.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from job_hunter.tracking.repository import insert_jobs
from job_hunter.ux.web.api import DashAPI

_STATUS_CYCLE = (
    "candidate",
    "candidate",
    "candidate",
    "shortlisted",
    "discarded",
    "tailored",
    "applied",
    "responded",
    "interview",
    "offer",
    "rejected",
)
_REASON_CYCLE = ("", "", "wrong_location", "wrong_role", "not_interested", "experience_mismatch")


def _seed_10k(root: Path) -> None:
    insert_jobs(
        root,
        [
            {
                "url": f"https://example.com/job/{i}",
                "title": f"Product Manager {i}",
                "company": f"Company {i % 500}",
                "country_code": ("DE", "US", "GB")[i % 3],
            }
            for i in range(10_000)
        ],
    )
    db_path = root / "outputs" / "state" / "jobs.db"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT id FROM jobs ORDER BY id").fetchall()
        for row_index, (job_id,) in enumerate(rows):
            status = _STATUS_CYCLE[row_index % len(_STATUS_CYCLE)]
            reason = _REASON_CYCLE[row_index % len(_REASON_CYCLE)] if status == "discarded" else ""
            score = (row_index * 37) % 100 if row_index % 4 else None
            slug = f"job-{job_id}" if status not in ("candidate", "shortlisted", "discarded") else None
            days_ago = row_index % 6
            conn.execute(
                "UPDATE jobs SET status=?, rejection_reason=?, score=?, slug=?, "
                "discovered_at=datetime('now', ?) WHERE id=?",
                (status, reason, score, slug, f"-{days_ago} days", job_id),
            )
        conn.commit()


def _timed(label: str, fn) -> float:  # noqa: ANN001 — test-local timing helper, callable type not worth spelling out
    start = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - start
    print(f"[perf] {label}: {elapsed * 1000:.1f}ms")  # noqa: T201 — intentional perf signal, run with -s to see it
    return elapsed


def test_dashboard_views_stay_fast_on_10k_jobs(tmp_path: Path) -> None:
    _seed_10k(tmp_path)
    api = DashAPI(tmp_path)

    assert _timed("get_today", lambda: api.get_today(page=1, page_size=20)) < 2.0
    assert _timed("get_unprocessed(active)", lambda: api.get_unprocessed("active")) < 2.0
    assert _timed("get_unprocessed(shortlisted)", lambda: api.get_unprocessed("shortlisted")) < 2.0
    assert _timed("get_unprocessed(discarded)", lambda: api.get_unprocessed("discarded")) < 2.0
    for status in ("tailored", "applied", "responded", "interview", "offer", "rejected"):
        assert _timed(f"get_applications({status})", lambda status=status: api.get_applications(status=status)) < 2.0
    assert _timed("get_insights", lambda: api.get_insights()) < 2.0
