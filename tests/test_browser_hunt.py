from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.pipeline import browser_hunt
from job_hunter.tracking.repository import get_discovered_jobs


def _write_config(root: Path, companies: list[dict]) -> None:
    config = root / "config"
    config.mkdir()
    (config / "job_hunter.yml").write_text(
        yaml.safe_dump({"job_titles": ["Product Manager"], "exclusions": {"title_terms": ["intern"]}}),
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
