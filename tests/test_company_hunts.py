"""Tests for tracking/company_hunts.py — company-hunt run/task persistence."""

from __future__ import annotations

from pathlib import Path

from job_hunter.tracking import company_hunts as ch

_COMPANIES = [
    {"name": "Stripe", "career_url": "https://stripe.com/jobs", "location": "Berlin"},
    {"name": "N26", "career_url": "https://n26.com/careers", "location": "Berlin", "enabled": False},
]


def test_begin_run_creates_running_row(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)

    run = ch.get_run(tmp_path, run_id)

    assert run["mode"] == ch.MODE_NEW_CHANGED
    assert run["status"] == "running"
    assert run["total"] == 0
    assert run["started_at"]
    assert run["finished_at"] is None


def test_create_tasks_precreates_rows_and_bumps_total(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)

    ch.create_tasks(tmp_path, run_id, _COMPANIES, status=ch.PENDING)

    tasks = ch.get_tasks_for_run(tmp_path, run_id)
    assert [t["company_name"] for t in tasks] == ["Stripe", "N26"]
    assert [t["status"] for t in tasks] == [ch.PENDING, ch.PENDING]
    assert [t["enabled"] for t in tasks] == [1, 0]
    run = ch.get_run(tmp_path, run_id)
    assert run["total"] == 2
    assert run["skipped"] == 0


def test_create_tasks_with_skipped_status_bumps_skipped_counter(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)

    ch.create_tasks(tmp_path, run_id, _COMPANIES, status=ch.SKIPPED)

    run = ch.get_run(tmp_path, run_id)
    assert run["total"] == 2
    assert run["skipped"] == 2


def test_create_tasks_with_empty_list_is_a_no_op(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)

    ch.create_tasks(tmp_path, run_id, [], status=ch.PENDING)

    assert ch.get_run(tmp_path, run_id)["total"] == 0
    assert ch.get_tasks_for_run(tmp_path, run_id) == []


def test_get_pending_tasks_returns_only_pending(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, [_COMPANIES[0]], status=ch.PENDING)
    ch.create_tasks(tmp_path, run_id, [_COMPANIES[1]], status=ch.SKIPPED)

    pending = ch.get_pending_tasks(tmp_path, run_id)

    assert [t["company_name"] for t in pending] == ["Stripe"]


def test_prepare_resume_requeues_task_interrupted_while_running(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, _COMPANIES, status=ch.PENDING)
    task_id = ch.get_pending_tasks(tmp_path, run_id)[0]["id"]
    ch.start_task(tmp_path, task_id)

    ch.prepare_resume(tmp_path, run_id)

    pending = ch.get_pending_tasks(tmp_path, run_id)
    assert pending[0]["id"] == task_id
    assert pending[0]["started_at"] is None


def test_start_task_marks_running_with_timestamp(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, [_COMPANIES[0]], status=ch.PENDING)
    task_id = ch.get_pending_tasks(tmp_path, run_id)[0]["id"]

    ch.start_task(tmp_path, task_id)

    task = ch.get_tasks_for_run(tmp_path, run_id)[0]
    assert task["status"] == ch.RUNNING
    assert task["started_at"]


def test_finish_task_persists_result_and_updates_run_aggregate(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, [_COMPANIES[0]], status=ch.PENDING)
    task_id = ch.get_pending_tasks(tmp_path, run_id)[0]["id"]
    ch.start_task(tmp_path, task_id)

    ch.finish_task(
        tmp_path,
        task_id,
        run_id,
        status=ch.OK,
        extraction_method="jsonld",
        duration_s=1.5,
        jobs_observed=3,
        jobs_inserted=2,
        etag='"abc123"',
        last_modified="Wed, 21 Oct 2026 07:28:00 GMT",
        fingerprint="deadbeef",
    )

    task = ch.get_tasks_for_run(tmp_path, run_id)[0]
    assert task["status"] == ch.OK
    assert task["extraction_method"] == "jsonld"
    assert task["duration_s"] == 1.5
    assert task["jobs_observed"] == 3
    assert task["jobs_inserted"] == 2
    assert task["etag"] == '"abc123"'
    assert task["finished_at"]

    run = ch.get_run(tmp_path, run_id)
    assert run["succeeded"] == 1
    assert run["failed"] == 0
    assert run["jobs_observed"] == 3
    assert run["jobs_inserted"] == 2


def test_finish_task_failure_increments_failed_not_succeeded(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, [_COMPANIES[0]], status=ch.PENDING)
    task_id = ch.get_pending_tasks(tmp_path, run_id)[0]["id"]

    ch.finish_task(tmp_path, task_id, run_id, status=ch.FAILED, failure_reason="couldn't be reached")

    run = ch.get_run(tmp_path, run_id)
    assert run["succeeded"] == 0
    assert run["failed"] == 1
    task = ch.get_tasks_for_run(tmp_path, run_id)[0]
    assert task["failure_reason"] == "couldn't be reached"


def test_finish_run_sets_status_and_finished_at(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)

    ch.finish_run(tmp_path, run_id, status="done")

    run = ch.get_run(tmp_path, run_id)
    assert run["status"] == "done"
    assert run["finished_at"]


def test_finish_run_can_record_error(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)

    ch.finish_run(tmp_path, run_id, status="error", error="company list is missing")

    run = ch.get_run(tmp_path, run_id)
    assert run["status"] == "error"
    assert run["error"] == "company list is missing"


def test_get_latest_run_returns_most_recent(tmp_path: Path) -> None:
    ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    second_id = ch.begin_run(tmp_path, ch.MODE_FORCE_ALL)

    latest = ch.get_latest_run(tmp_path)

    assert latest["id"] == second_id
    assert latest["mode"] == ch.MODE_FORCE_ALL


def test_get_latest_run_returns_none_when_no_runs_exist(tmp_path: Path) -> None:
    assert ch.get_latest_run(tmp_path) is None


def test_find_resumable_run_returns_running_run_only(tmp_path: Path) -> None:
    finished_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.finish_run(tmp_path, finished_id, status="done")
    running_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)

    resumable = ch.find_resumable_run(tmp_path)

    assert resumable["id"] == running_id


def test_find_resumable_run_returns_none_when_nothing_interrupted(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.finish_run(tmp_path, run_id, status="done")

    assert ch.find_resumable_run(tmp_path) is None


def test_get_last_task_for_url_returns_most_recent_terminal_task(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, [_COMPANIES[0]], status=ch.PENDING)
    task_id = ch.get_pending_tasks(tmp_path, run_id)[0]["id"]
    ch.finish_task(tmp_path, task_id, run_id, status=ch.OK, jobs_observed=1, jobs_inserted=1)

    last = ch.get_last_task_for_url(tmp_path, "https://stripe.com/jobs")

    assert last["status"] == ch.OK
    assert last["career_url"] == "https://stripe.com/jobs"


def test_get_last_task_for_url_ignores_pending_and_running_tasks(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, [_COMPANIES[0]], status=ch.PENDING)

    assert ch.get_last_task_for_url(tmp_path, "https://stripe.com/jobs") is None


def test_get_last_task_for_url_returns_none_for_unknown_url(tmp_path: Path) -> None:
    assert ch.get_last_task_for_url(tmp_path, "https://unknown.example.com") is None


def test_get_latest_task_by_url_maps_each_url_to_its_newest_terminal_task(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, _COMPANIES, status=ch.PENDING)
    tasks = ch.get_pending_tasks(tmp_path, run_id)
    ch.finish_task(tmp_path, tasks[0]["id"], run_id, status=ch.OK, jobs_observed=2, jobs_inserted=1)
    ch.finish_task(tmp_path, tasks[1]["id"], run_id, status=ch.FAILED, failure_reason="timeout")

    latest = ch.get_latest_task_by_url(tmp_path)

    assert latest["https://stripe.com/jobs"]["status"] == ch.OK
    assert latest["https://n26.com/careers"]["status"] == ch.FAILED


def test_get_updates_since_returns_terminal_updates_in_completion_order(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, _COMPANIES, status=ch.PENDING)
    tasks = ch.get_pending_tasks(tmp_path, run_id)
    ch.finish_task(tmp_path, tasks[1]["id"], run_id, status=ch.OK, jobs_observed=1, jobs_inserted=1)
    first_batch = ch.get_updates_since(tmp_path, run_id)
    ch.finish_task(tmp_path, tasks[0]["id"], run_id, status=ch.OK, jobs_observed=1, jobs_inserted=1)
    second_batch = ch.get_updates_since(tmp_path, run_id, after_id=first_batch[0]["update_id"])

    assert [row["id"] for row in first_batch] == [tasks[1]["id"]]
    assert [row["id"] for row in second_batch] == [tasks[0]["id"]]
    assert second_batch[0]["update_id"] > first_batch[0]["update_id"]


def test_finish_task_is_idempotent_for_aggregates_and_updates(tmp_path: Path) -> None:
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)
    ch.create_tasks(tmp_path, run_id, [_COMPANIES[0]], status=ch.PENDING)
    task_id = ch.get_pending_tasks(tmp_path, run_id)[0]["id"]

    ch.finish_task(tmp_path, task_id, run_id, status=ch.OK, jobs_observed=2, jobs_inserted=1)
    ch.finish_task(tmp_path, task_id, run_id, status=ch.OK, jobs_observed=2, jobs_inserted=1)

    assert ch.get_run(tmp_path, run_id)["succeeded"] == 1
    assert len(ch.get_updates_since(tmp_path, run_id)) == 1


def test_create_tasks_snapshots_non_dict_company_entries(tmp_path: Path) -> None:
    """Malformed career_pages.yml entries (a bare string) must not crash task creation."""
    run_id = ch.begin_run(tmp_path, ch.MODE_NEW_CHANGED)

    ch.create_tasks(tmp_path, run_id, ["not-a-dict"], status=ch.PENDING)

    task = ch.get_tasks_for_run(tmp_path, run_id)[0]
    assert task["company_name"] == "not-a-dict"
    assert task["career_url"] == ""
