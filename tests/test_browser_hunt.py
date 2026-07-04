from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.pipeline import browser_hunt
from job_hunter.tracking.repository import get_discovered_jobs


def _write_config(root: Path, companies: list[dict], exclusions: dict | None = None) -> None:
    config = root / "config"
    config.mkdir()
    (config / "job_hunter.yml").write_text(
        yaml.safe_dump(
            {
                "job_titles": ["Product Manager"],
                "exclusions": exclusions or {"title_terms": ["intern"]},
            }
        ),
        encoding="utf-8",
    )
    (config / "career_pages.yml").write_text(
        yaml.safe_dump({"companies": companies}),
        encoding="utf-8",
    )


def test_browser_hunt_requires_company_config(tmp_path: Path, monkeypatch) -> None:
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
    assert steps == ["started", "company-checking", "company-failed", "company-checking", "company-done", "finished"]
    failed_event = events[2]
    assert failed_event["reason"] == "took too long to respond"
    assert "connection timed out after 30s" not in str(events)
    finished = events[-1]
    assert finished["succeeded"] == 1
    assert finished["failed"] == 1
    assert finished["total"] == 2


def test_browser_hunt_invalid_yaml_emits_fatal_event_and_returns_1(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "job_hunter.yml").write_text("job_titles: [Product Manager]", encoding="utf-8")
    (config_dir / "career_pages.yml").write_text("companies: [unterminated", encoding="utf-8")
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
