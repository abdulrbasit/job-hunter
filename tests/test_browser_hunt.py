from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_hunter.pipeline import browser_hunt


def _write_config(root: Path, companies: list[dict]) -> None:
    config = root / "config"
    config.mkdir()
    (config / "job_hunter.yml").write_text(
        yaml.safe_dump({"job_titles": ["Product Manager"], "exclusions": {"title_terms": ["intern"]}}),
        encoding="utf-8",
    )
    (config / "companies_browser.yml").write_text(
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
    assert not (tmp_path / "outputs" / "browser_hunt" / "jobs.json").exists()


def test_browser_hunt_writes_combined_results(tmp_path: Path, monkeypatch) -> None:
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
                "excluded": exclusions,
            }
        ],
    )

    assert browser_hunt.run() == 0
    payload = json.loads((tmp_path / "outputs" / "browser_hunt" / "jobs.json").read_text(encoding="utf-8"))
    assert payload == [
        {
            "title": "Product Manager",
            "company": "Example",
            "url": "https://example.com/jobs/1",
            "excluded": ["intern"],
        }
    ]
