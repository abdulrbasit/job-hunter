"""Tests for the candidate/discarded status lifecycle: promotion, discard-by-id, retention cleanup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from job_hunter.tracking.repository import (
    _conn,
    delete_discarded_older_than,
    get_jobs_summary,
    insert_candidate_urls,
    set_status_by_id,
    upsert_job,
)


def test_upsert_job_promotes_candidate_to_tailored(tmp_path: Path) -> None:
    insert_candidate_urls(tmp_path, {"https://example.com/job"})
    upsert_job(tmp_path, {"url": "https://example.com/job", "slug": "2026-01-01_acme_pm", "status": "tailored"})
    jobs = get_jobs_summary(tmp_path, statuses=("tailored",))
    assert len(jobs) == 1


def test_upsert_job_never_demotes_an_advanced_status(tmp_path: Path) -> None:
    insert_candidate_urls(tmp_path, {"https://example.com/job"})
    upsert_job(tmp_path, {"url": "https://example.com/job", "slug": "s1", "status": "applied"})
    # Re-running a tailor-stage upsert must not demote applied -> tailored.
    upsert_job(tmp_path, {"url": "https://example.com/job", "slug": "s1", "status": "tailored"})
    jobs = get_jobs_summary(tmp_path, statuses=("applied",))
    assert len(jobs) == 1


def test_set_status_by_id_discards_a_candidate(tmp_path: Path) -> None:
    insert_candidate_urls(tmp_path, {"https://example.com/job"})
    jobs = get_jobs_summary(tmp_path, statuses=("candidate",))
    set_status_by_id(tmp_path, jobs[0]["id"], "discarded")
    assert get_jobs_summary(tmp_path, statuses=("candidate",)) == []
    assert len(get_jobs_summary(tmp_path, statuses=("discarded",))) == 1


def test_delete_discarded_older_than_removes_only_old_discarded_rows(tmp_path: Path) -> None:
    insert_candidate_urls(tmp_path, {"https://example.com/old", "https://example.com/new", "https://example.com/kept"})
    jobs = {j["url"]: j["id"] for j in get_jobs_summary(tmp_path, statuses=("candidate",))}
    set_status_by_id(tmp_path, jobs["https://example.com/old"], "discarded")
    set_status_by_id(tmp_path, jobs["https://example.com/new"], "discarded")

    old_cutoff = (datetime.now(UTC) - timedelta(days=120)).replace(microsecond=0).isoformat()
    with _conn(tmp_path) as conn:
        conn.execute(
            "UPDATE jobs SET processed_at=?, updated_at=? WHERE url=?",
            (old_cutoff, old_cutoff, "https://example.com/old"),
        )

    deleted = delete_discarded_older_than(tmp_path, days=90)

    assert deleted == 1
    remaining_urls = {j["url"] for j in get_jobs_summary(tmp_path, statuses=("discarded", "candidate"))}
    assert remaining_urls == {"https://example.com/new", "https://example.com/kept"}
