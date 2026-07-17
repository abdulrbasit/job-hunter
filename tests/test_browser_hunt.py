from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from job_hunter.pipeline import browser_hunt
from job_hunter.tracking import company_hunts
from job_hunter.tracking.repository import get_discovered_jobs

_FILTER_KEY_MAP = {
    "companies": "excluded_companies",
    "title_terms": "excluded_titles",
    "industries": "excluded_industries",
}


def _target(company: object) -> object:
    """Map a legacy {name, career_url, location?, enabled?} test fixture to a
    companies.targets entry {name, url, country, enabled?}. Malformed (non-dict)
    entries pass through unchanged — they exercise the "don't abort on bad data" tests."""
    if not isinstance(company, dict):
        return company
    entry: dict[str, object] = {"name": company.get("name"), "url": company.get("career_url"), "country": "DE"}
    if "enabled" in company:
        entry["enabled"] = company["enabled"]
    return entry


def _write_config(
    root: Path, companies: list[object], exclusions: dict | None = None, regions: dict | None = None
) -> None:
    config = root / "config"
    config.mkdir()
    filters = {}
    for legacy_key, value in (exclusions or {"title_terms": ["intern"]}).items():
        filters[_FILTER_KEY_MAP.get(legacy_key, legacy_key)] = value
    data: dict[str, object] = {
        "job_titles": ["Product Manager"],
        "regions": regions or {"de": {"enabled": True, "country": "DE", "scope": "country"}},
        "filters": filters,
    }
    targets = [_target(company) for company in companies]
    if targets:
        data["companies"] = {"targets": targets}
    (config / "job_hunter.yml").write_text(yaml.safe_dump(data), encoding="utf-8")


def test_browser_hunt_requires_job_hunter_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)

    assert browser_hunt.run() == 1


def test_browser_hunt_skips_empty_company_list(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, [])
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)

    assert browser_hunt.run() == 0
    assert not (tmp_path / "outputs" / "state" / "jobs.db").exists()


def test_browser_hunt_writes_results_into_jobs_db(tmp_path: Path, monkeypatch) -> None:
    """Browser-hunt candidates must land in the same jobs.db the regular find-jobs hunt
    writes to — not an isolated file — so they flow through the same dedup/screen/score
    pipeline as any other discovered candidate."""
    companies = [{"name": "Example", "career_url": "https://example.com/jobs", "location": "Berlin"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: [
            {
                "title": titles[0],
                "company": company["name"],
                "url": "https://example.com/jobs/1",
            }
        ],
    )

    assert browser_hunt.run() == 0
    jobs = get_discovered_jobs(tmp_path)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Manager"
    assert jobs[0]["company"] == "Example"
    assert jobs[0]["url"] == "https://example.com/jobs/1"
    assert jobs[0]["status"] == "candidate"


def test_browser_hunt_dedupes_against_existing_jobs_db_rows(tmp_path: Path, monkeypatch) -> None:
    """Running browser-hunt twice for the same URL must not create duplicate rows —
    insert_jobs' upsert-on-url is the single dedup mechanism, same as the regular hunt."""
    companies = [{"name": "Example", "career_url": "https://example.com/jobs", "location": "Berlin"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: [
            {"title": titles[0], "company": company["name"], "url": "https://example.com/jobs/1"}
        ],
    )

    assert browser_hunt.run() == 0
    assert browser_hunt.run() == 0

    assert len(get_discovered_jobs(tmp_path)) == 1


def test_browser_hunt_one_company_failure_does_not_abort_remaining_companies(tmp_path: Path, monkeypatch) -> None:
    """One company raising must not abort the whole hunt for every remaining company."""
    companies = [
        {"name": "Broken Corp", "career_url": "https://broken.example.com/jobs", "location": "Berlin"},
        {"name": "Kept Corp", "career_url": "https://kept.example.com/jobs", "location": "Berlin"},
    ]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)

    def fake_extract(company, titles, exclusions):
        if company["name"] == "Broken Corp":
            raise RuntimeError("boom")
        return [{"title": titles[0], "company": company["name"], "url": "https://kept.example.com/jobs/1"}]

    monkeypatch.setattr(browser_hunt, "extract_career_page_jobs", fake_extract)

    assert browser_hunt.run() == 0
    jobs = get_discovered_jobs(tmp_path)
    assert [job["company"] for job in jobs] == ["Kept Corp"]


def test_browser_hunt_malformed_company_entry_does_not_abort_run(tmp_path: Path, monkeypatch) -> None:
    companies = ["not-a-dict", {"name": "Kept Corp", "career_url": "https://kept.example.com/jobs", "location": ""}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)

    def fake_extract(company, titles, exclusions):
        if not isinstance(company, dict):
            raise AttributeError("'str' object has no attribute 'get'")
        return [{"title": titles[0], "company": company["name"], "url": "https://kept.example.com/jobs/1"}]

    monkeypatch.setattr(browser_hunt, "extract_career_page_jobs", fake_extract)

    assert browser_hunt.run() == 0
    jobs = get_discovered_jobs(tmp_path)
    assert [job["company"] for job in jobs] == ["Kept Corp"]


def test_browser_hunt_emits_progress_events_for_each_company(tmp_path: Path, monkeypatch) -> None:
    companies = [
        {"name": "Broken Corp", "career_url": "https://broken.example.com/jobs", "location": ""},
        {"name": "Kept Corp", "career_url": "https://kept.example.com/jobs", "location": ""},
    ]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)

    def fake_extract(company, titles, exclusions):
        if company["name"] == "Broken Corp":
            raise TimeoutError("connection timed out after 30s")
        return [{"title": titles[0], "company": company["name"], "url": "https://kept.example.com/jobs/1"}]

    monkeypatch.setattr(browser_hunt, "extract_career_page_jobs", fake_extract)

    events: list[dict] = []
    browser_hunt.run(on_progress=events.append)

    steps = [e["step"] for e in events]
    assert steps[0] == "started"
    assert steps[-1] == "finished"
    assert steps.count("company-checking") == 2
    assert steps.count("company-failed") == 1
    assert steps.count("company-done") == 1
    failed_event = next(event for event in events if event["step"] == "company-failed")
    assert failed_event["reason"] == "took too long to respond"
    assert "connection timed out after 30s" not in str(events)
    finished = events[-1]
    assert finished["succeeded"] == 1
    assert finished["failed"] == 1
    assert finished["total"] == 2


def test_browser_hunt_invalid_yaml_emits_fatal_event_and_returns_1(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "job_hunter.yml").write_text("job_titles: [unterminated", encoding="utf-8")
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)

    events: list[dict] = []
    assert browser_hunt.run(on_progress=events.append) == 1
    assert events == [{"step": "fatal", "reason": events[0]["reason"]}]
    assert "unterminated" not in events[0]["reason"]


def test_browser_hunt_skips_disabled_companies(tmp_path: Path, monkeypatch) -> None:
    companies = [
        {"name": "Disabled Corp", "career_url": "https://disabled.example.com/jobs", "enabled": False},
        {"name": "Kept Corp", "career_url": "https://kept.example.com/jobs", "enabled": True},
    ]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: [
            {"title": titles[0], "company": company["name"], "url": f"https://example.com/jobs/{company['name']}"}
        ],
    )

    events: list[dict] = []
    assert browser_hunt.run(on_progress=events.append) == 0

    jobs = get_discovered_jobs(tmp_path)
    assert [job["company"] for job in jobs] == ["Kept Corp"]
    assert events[0] == {"step": "started", "total": 1}
    assert all(e.get("company") != "Disabled Corp" for e in events)


def test_browser_hunt_defaults_missing_enabled_key_to_true(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Legacy Corp", "career_url": "https://legacy.example.com/jobs"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: [
            {"title": titles[0], "company": company["name"], "url": "https://legacy.example.com/jobs/1"}
        ],
    )

    assert browser_hunt.run() == 0
    jobs = get_discovered_jobs(tmp_path)
    assert [job["company"] for job in jobs] == ["Legacy Corp"]


def test_browser_hunt_excludes_companies_before_insert(tmp_path: Path, monkeypatch) -> None:
    """A company listed in exclusions.companies is scraped but must never reach jobs.db —
    exclusion screening runs right after scraping, before insert_jobs()."""
    companies = [
        {"name": "Excluded Corp", "career_url": "https://excluded.example.com/jobs", "location": "Berlin"},
        {"name": "Kept Corp", "career_url": "https://kept.example.com/jobs", "location": "Berlin"},
    ]
    _write_config(tmp_path, companies, exclusions={"companies": ["Excluded Corp"]})
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: [
            {
                "title": titles[0],
                "company": company["name"],
                "url": f"https://example.com/jobs/{company['name']}",
            }
        ],
    )

    assert browser_hunt.run() == 0
    jobs = get_discovered_jobs(tmp_path)
    assert [job["company"] for job in jobs] == ["Kept Corp"]


def test_browser_hunt_rejects_extracted_job_outside_enabled_city(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Berlin Corp", "career_url": "https://berlin.example/jobs", "location": "Berlin"}]
    _write_config(
        tmp_path,
        companies,
        regions={"berlin": {"enabled": True, "country": "DE", "scope": "city", "city_id": "geonames:2950159"}},
    )
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda _company, titles, _exclusions: [
            {
                "title": titles[0],
                "company": "Berlin Corp",
                "url": "https://berlin.example/jobs/stuttgart",
                "location": "Stuttgart, Germany",
            }
        ],
    )

    assert browser_hunt.run() == 0
    assert get_discovered_jobs(tmp_path) == []


# ---------------------------------------------------------------------------
# Phase 5: persistence, run modes, cooldown, resume
# ---------------------------------------------------------------------------


def test_browser_hunt_persists_a_run_and_task_row_on_success(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Acme", "career_url": "https://acme.example.com/jobs", "location": "Berlin"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: [
            {
                "title": titles[0],
                "company": company["name"],
                "url": "https://acme.example.com/jobs/1",
                "extraction_method": "jsonld",
            }
        ],
    )

    assert browser_hunt.run() == 0

    run = company_hunts.get_latest_run(tmp_path)
    assert run["mode"] == company_hunts.MODE_NEW_CHANGED
    assert run["status"] == "done"
    assert run["total"] == 1
    assert run["succeeded"] == 1
    assert run["failed"] == 0
    assert run["jobs_inserted"] == 1

    task = company_hunts.get_tasks_for_run(tmp_path, run["id"])[0]
    assert task["company_name"] == "Acme"
    assert task["career_url"] == "https://acme.example.com/jobs"
    assert task["status"] == company_hunts.OK
    assert task["extraction_method"] == "jsonld"
    assert task["jobs_observed"] == 1
    assert task["jobs_inserted"] == 1
    assert task["duration_s"] is not None


def test_browser_hunt_deadline_measures_own_processing_time_not_queue_wait(tmp_path: Path, monkeypatch) -> None:
    """Regression: with a small worker pool and a long queue, duration used to be measured
    from task creation — so a company queued behind a slow one could get marked "took too
    long to respond" even though its own fetch was instant, just because it waited a long
    time for a free worker. duration must be timed from when a worker actually starts that
    company's own attempt."""
    companies = [
        {"name": "Slow First", "career_url": "https://slow.example.com/jobs"},
        {"name": "Fast Second", "career_url": "https://fast.example.com/jobs"},
    ]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "CHEAP_WORKERS", 1)  # forces strictly sequential processing
    monkeypatch.setattr(browser_hunt, "COMPANY_DEADLINE_SECONDS", 0.2)

    def fake_extract(company, titles, exclusions):
        if company["name"] == "Slow First":
            time.sleep(0.35)
        return []

    monkeypatch.setattr(browser_hunt, "extract_career_page_jobs", fake_extract)

    assert browser_hunt.run() == 0

    run = company_hunts.get_latest_run(tmp_path)
    tasks = {t["company_name"]: t for t in company_hunts.get_tasks_for_run(tmp_path, run["id"])}
    assert tasks["Slow First"]["status"] == company_hunts.FAILED
    assert tasks["Slow First"]["failure_reason"] == "took too long to respond"
    # Fast Second waited ~0.35s in queue behind Slow First, but its own processing was
    # instant — the old (buggy) duration measurement would have failed this one too.
    assert tasks["Fast Second"]["status"] == company_hunts.OK


def test_browser_hunt_persists_a_failed_task_with_reason(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Broken", "career_url": "https://broken.example.com/jobs"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)

    def boom(company, titles, exclusions):
        raise TimeoutError("connection timed out after 30s")

    monkeypatch.setattr(browser_hunt, "extract_career_page_jobs", boom)

    assert browser_hunt.run() == 0

    run = company_hunts.get_latest_run(tmp_path)
    assert run["failed"] == 1
    task = company_hunts.get_tasks_for_run(tmp_path, run["id"])[0]
    assert task["status"] == company_hunts.FAILED
    assert task["failure_reason"] == "took too long to respond"


def test_new_changed_mode_skips_a_recently_succeeded_company(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Acme", "career_url": "https://acme.example.com/jobs"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    calls: list[str] = []
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: (calls.append(company["name"]), [])[1],
    )

    assert browser_hunt.run() == 0
    assert calls == ["Acme"]

    assert browser_hunt.run() == 0

    assert calls == ["Acme"]  # second run skipped it — no second extract call
    second_run = company_hunts.get_latest_run(tmp_path)
    assert second_run["skipped"] == 1
    assert second_run["total"] == 1


def test_new_changed_mode_reprocesses_after_cooldown_expires(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Acme", "career_url": "https://acme.example.com/jobs"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    calls: list[str] = []
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: (calls.append(company["name"]), [])[1],
    )

    assert browser_hunt.run() == 0
    first_run = company_hunts.get_latest_run(tmp_path)
    task_id = company_hunts.get_tasks_for_run(tmp_path, first_run["id"])[0]["id"]
    stale = (datetime.now(UTC) - timedelta(hours=100)).replace(microsecond=0).isoformat()
    with company_hunts._conn(tmp_path) as conn:
        conn.execute("UPDATE company_hunt_tasks SET finished_at = ? WHERE id = ?", (stale, task_id))

    assert browser_hunt.run(cooldown_hours=24) == 0

    assert calls == ["Acme", "Acme"]


def test_failed_only_mode_reprocesses_failures_and_skips_successes(tmp_path: Path, monkeypatch) -> None:
    companies = [
        {"name": "Broken", "career_url": "https://broken.example.com/jobs"},
        {"name": "Working", "career_url": "https://working.example.com/jobs"},
    ]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)

    def fake_extract(company, titles, exclusions):
        if company["name"] == "Broken":
            raise RuntimeError("boom")
        return []

    monkeypatch.setattr(browser_hunt, "extract_career_page_jobs", fake_extract)
    assert browser_hunt.run() == 0

    calls: list[str] = []
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: (calls.append(company["name"]), [])[1],
    )

    assert browser_hunt.run(mode=company_hunts.MODE_FAILED_ONLY) == 0

    assert calls == ["Broken"]


def test_force_all_mode_reprocesses_everyone_regardless_of_recent_success(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Acme", "career_url": "https://acme.example.com/jobs"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    calls: list[str] = []
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: (calls.append(company["name"]), [])[1],
    )

    assert browser_hunt.run() == 0
    assert browser_hunt.run(mode=company_hunts.MODE_FORCE_ALL) == 0

    assert calls == ["Acme", "Acme"]
    second_run = company_hunts.get_latest_run(tmp_path)
    assert second_run["mode"] == company_hunts.MODE_FORCE_ALL
    assert second_run["skipped"] == 0


def test_resume_mode_continues_an_interrupted_run_without_recreating_it(tmp_path: Path, monkeypatch) -> None:
    companies = [
        {"name": "First", "career_url": "https://first.example.com/jobs"},
        {"name": "Second", "career_url": "https://second.example.com/jobs"},
    ]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)

    # Simulate a crash: a run exists with one task already 'ok' and one still 'pending'.
    interrupted_run_id = company_hunts.begin_run(tmp_path, company_hunts.MODE_NEW_CHANGED)
    company_hunts.create_tasks(tmp_path, interrupted_run_id, [companies[0]], status=company_hunts.PENDING)
    company_hunts.create_tasks(tmp_path, interrupted_run_id, [companies[1]], status=company_hunts.PENDING)
    tasks = company_hunts.get_pending_tasks(tmp_path, interrupted_run_id)
    company_hunts.finish_task(tmp_path, tasks[0]["id"], interrupted_run_id, status=company_hunts.OK, jobs_observed=0)
    # run row deliberately left with status='running' — no finish_run() call, as if the process died here

    calls: list[str] = []
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: (calls.append(company["name"]), [])[1],
    )

    assert browser_hunt.run(mode=company_hunts.MODE_RESUME) == 0

    assert calls == ["Second"]  # only the still-pending task was (re)processed
    run = company_hunts.get_run(tmp_path, interrupted_run_id)
    assert run["id"] == interrupted_run_id  # same run continued, not a new one
    assert run["status"] == "done"
    assert run["succeeded"] == 2  # 1 from before the crash + 1 from resuming
    assert company_hunts.get_latest_run(tmp_path)["id"] == interrupted_run_id


def test_resume_mode_retries_task_interrupted_while_running(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Interrupted", "career_url": "https://interrupted.example.com/jobs"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    run_id = company_hunts.begin_run(tmp_path, company_hunts.MODE_NEW_CHANGED)
    company_hunts.create_tasks(tmp_path, run_id, companies, status=company_hunts.PENDING)
    task_id = company_hunts.get_pending_tasks(tmp_path, run_id)[0]["id"]
    company_hunts.start_task(tmp_path, task_id)
    calls: list[str] = []
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions: (calls.append(company["name"]), [])[1],
    )

    assert browser_hunt.run(mode=company_hunts.MODE_RESUME) == 0

    assert calls == ["Interrupted"]
    assert company_hunts.get_run(tmp_path, run_id)["succeeded"] == 1


def test_resume_mode_falls_back_to_new_changed_when_nothing_is_interrupted(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Acme", "career_url": "https://acme.example.com/jobs"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(browser_hunt, "extract_career_page_jobs", lambda company, titles, exclusions: [])

    assert browser_hunt.run(mode=company_hunts.MODE_RESUME) == 0

    run = company_hunts.get_latest_run(tmp_path)
    assert run["mode"] == company_hunts.MODE_NEW_CHANGED
    assert run["status"] == "done"


def test_browser_hunt_overlaps_cheap_company_checks(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": f"Company {index}", "career_url": f"https://example.com/{index}"} for index in range(50)]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    active = 0
    peak = 0
    lock = threading.Lock()

    def extract(company, titles, exclusions, *, use_playwright=True):
        nonlocal active, peak
        assert use_playwright is False
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return [{"title": titles[0], "company": company["name"], "url": company["career_url"] + "/job"}]

    monkeypatch.setattr(browser_hunt, "extract_career_page_jobs", extract)
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: pytest.fail("cheap success used Chromium"))

    assert browser_hunt.run() == 0

    assert 1 < peak <= browser_hunt.CHEAP_WORKERS


def test_browser_hunt_only_probes_chromium_when_fallback_queue_exists(tmp_path: Path, monkeypatch) -> None:
    companies = [{"name": "Needs JS", "career_url": "https://example.com/jobs"}]
    _write_config(tmp_path, companies)
    monkeypatch.setattr(browser_hunt, "ROOT", tmp_path)
    probes: list[bool] = []
    monkeypatch.setattr(
        browser_hunt,
        "extract_career_page_jobs",
        lambda company, titles, exclusions, *, use_playwright=True: [],
    )
    monkeypatch.setattr(browser_hunt, "ensure_chromium_installed", lambda: probes.append(True) or True)

    def fake_batch(companies, titles, exclusions, *, on_result=None):
        # Real extract_playwright_jobs_batch's signature includes on_result (and now a
        # per-company duration) — a mock missing it previously masked a TypeError into a
        # silently-"failed" task.
        results = [(company, []) for company in companies]
        if on_result:
            for company, jobs in results:
                on_result(company, jobs, 0.01)
        return results

    monkeypatch.setattr(browser_hunt, "extract_playwright_jobs_batch", fake_batch)

    assert browser_hunt.run() == 0

    assert probes == [True]
    run = company_hunts.get_latest_run(tmp_path)
    task = company_hunts.get_tasks_for_run(tmp_path, run["id"])[0]
    assert task["status"] == company_hunts.OK  # proves the fallback path actually succeeded, not just that it ran
