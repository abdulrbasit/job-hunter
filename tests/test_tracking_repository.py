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


def test_discard_job_ids_discards_all_given_ids_in_one_call(tmp_path: Path) -> None:
    repository.insert_jobs(
        tmp_path,
        [
            {"url": "https://example.com/a", "title": "PM", "company": "A"},
            {"url": "https://example.com/b", "title": "PM", "company": "B"},
        ],
    )
    jobs = repository.get_jobs_summary(tmp_path, statuses=("candidate",))
    ids = [job["id"] for job in jobs]

    result = repository.discard_job_ids(tmp_path, ids)

    assert result["discarded"] == 2
    assert result["skipped"] == []
    assert len(repository.get_jobs_summary(tmp_path, statuses=("discarded",))) == 2
    assert repository.get_jobs_summary(tmp_path, statuses=("candidate",)) == []


def test_discard_job_ids_skips_unknown_ids_without_failing_the_batch(tmp_path: Path) -> None:
    repository.insert_jobs(tmp_path, [{"url": "https://example.com/a", "title": "PM", "company": "A"}])
    real_id = repository.get_jobs_summary(tmp_path, statuses=("candidate",))[0]["id"]

    result = repository.discard_job_ids(tmp_path, [real_id, 999999])

    assert result["discarded"] == 1
    assert result["skipped"] == [999999]


def test_discard_job_ids_never_downgrades_a_job_past_candidate_stage(tmp_path: Path) -> None:
    """A stale id for a job that has already advanced past candidate/discovered must not
    be reverted to discarded — same downgrade guard as mark_candidates_discarded."""
    repository.upsert_job(tmp_path, {"url": "https://example.com/c", "slug": "acme-pm", "status": "tailored"})
    job = repository.get_job_by_slug(tmp_path, "acme-pm")

    result = repository.discard_job_ids(tmp_path, [job["id"]])

    assert result["discarded"] == 0
    assert result["skipped"] == [job["id"]]
    assert repository.get_job_by_slug(tmp_path, "acme-pm")["status"] == "tailored"


def test_delete_jobs_by_slugs_deletes_all_matching_rows(tmp_path: Path) -> None:
    repository.upsert_job(tmp_path, {"url": "https://example.com/a", "slug": "a-pm", "status": "tailored"})
    repository.upsert_job(tmp_path, {"url": "https://example.com/b", "slug": "b-pm", "status": "tailored"})
    repository.upsert_job(tmp_path, {"url": "https://example.com/c", "slug": "c-pm", "status": "tailored"})

    deleted = repository.delete_jobs_by_slugs(tmp_path, ["a-pm", "b-pm"])

    assert deleted == 2
    assert repository.get_job_by_slug(tmp_path, "a-pm") is None
    assert repository.get_job_by_slug(tmp_path, "b-pm") is None
    assert repository.get_job_by_slug(tmp_path, "c-pm") is not None


def test_delete_jobs_by_slugs_tolerates_unknown_slugs(tmp_path: Path) -> None:
    repository.upsert_job(tmp_path, {"url": "https://example.com/a", "slug": "a-pm", "status": "tailored"})

    deleted = repository.delete_jobs_by_slugs(tmp_path, ["a-pm", "does-not-exist"])

    assert deleted == 1


def test_delete_jobs_by_slugs_returns_zero_for_empty_list(tmp_path: Path) -> None:
    assert repository.delete_jobs_by_slugs(tmp_path, []) == 0


def test_insert_jobs_persists_extraction_method(tmp_path: Path) -> None:
    repository.insert_jobs(
        tmp_path,
        [{"url": "https://example.com/a", "title": "PM", "company": "A", "extraction_method": "jsonld"}],
    )

    job = repository.get_job_by_url(tmp_path, "https://example.com/a")

    assert job["extraction_method"] == "jsonld"


def test_insert_jobs_extraction_method_defaults_to_empty_string(tmp_path: Path) -> None:
    repository.insert_jobs(tmp_path, [{"url": "https://example.com/a", "title": "PM", "company": "A"}])

    job = repository.get_job_by_url(tmp_path, "https://example.com/a")

    assert job["extraction_method"] == ""


def test_existing_jobs_db_without_extraction_method_column_upgrades_safely(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "outputs" / "state" / "jobs.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    try:
        # repository._DDL predates the extraction_method column — it's added only via
        # the additive _migrate() ALTER TABLE, so executing _DDL alone reproduces a
        # pre-migration jobs.db exactly.
        conn.executescript(repository._DDL)
        conn.commit()
    finally:
        conn.close()

    repository.insert_jobs(tmp_path, [{"url": "https://example.com/a", "title": "PM", "company": "A"}])

    job = repository.get_job_by_url(tmp_path, "https://example.com/a")
    assert job is not None
    assert job["extraction_method"] == ""


def test_insert_jobs_with_new_count_distinguishes_new_from_reprocessed(tmp_path: Path) -> None:
    first = repository.insert_jobs_with_new_count(
        tmp_path, [{"url": "https://example.com/a", "title": "PM", "company": "A"}]
    )
    assert first == {"processed": 1, "new": 1}

    second = repository.insert_jobs_with_new_count(
        tmp_path,
        [
            {"url": "https://example.com/a", "title": "PM", "company": "A"},
            {"url": "https://example.com/b", "title": "PM", "company": "B"},
        ],
    )

    assert second == {"processed": 2, "new": 1}


def test_get_company_hunt_candidates_selects_only_pending_career_page_rows(tmp_path: Path) -> None:
    repository.insert_jobs(
        tmp_path,
        [
            {"url": "https://example.com/company", "title": "PM", "source": "career_page:jsonld"},
            {"url": "https://example.com/board", "title": "PM", "source": "linkedin"},
        ],
    )
    repository.upsert_job(
        tmp_path,
        {
            "url": "https://example.com/already-tailored",
            "title": "PM",
            "source": "career_page:static_html",
            "slug": "already-tailored",
            "status": "tailored",
        },
    )

    candidates = repository.get_company_hunt_candidates(tmp_path)

    assert [job["url"] for job in candidates] == ["https://example.com/company"]
