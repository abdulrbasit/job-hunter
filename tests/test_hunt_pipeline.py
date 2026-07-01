from __future__ import annotations

import json

from job_hunter.models import ScrapeStats
from job_hunter.pipeline import hunt as hunt_pipeline


def test_run_hunt_scrape_only_writes_snapshot_with_tracker_context(monkeypatch, tmp_path) -> None:
    from job_hunter.tracking.repository import get_discovered_jobs

    jobs = [{"title": "PM", "company": "Acme", "url": "https://example.com/pm"}]
    enriched = [{**jobs[0], "snippet": "rich"}]

    monkeypatch.setattr(
        hunt_pipeline,
        "_jobs_from_hunt",
        lambda region, depth="standard": (
            jobs,
            {"https://example.com/old"},
            set(),
            ScrapeStats(total_fetched=1, total_after_policy=1),
        ),
    )
    monkeypatch.setattr(hunt_pipeline, "_drop_dead_urls", lambda jobs, api_config, checker: jobs)
    monkeypatch.setattr(hunt_pipeline, "_enrich", lambda jobs, api_config: enriched)
    monkeypatch.setattr(hunt_pipeline, "load_cached_candidate_urls", lambda: set())
    monkeypatch.setattr(hunt_pipeline, "save_cached_candidate_urls", lambda _urls: None)

    run_id, count, _stats = hunt_pipeline.run_hunt_scrape_only(
        "primary",
        tmp_path,
        api_config={},
        url_checker=lambda *_args: True,
    )

    assert count == 1
    assert isinstance(run_id, str) and "T" in run_id
    db_jobs = get_discovered_jobs(tmp_path, run_id=run_id)
    assert len(db_jobs) == 1
    assert db_jobs[0]["title"] == "PM"


def test_run_hunt_scrape_only_writes_empty_snapshot(monkeypatch, tmp_path) -> None:
    from job_hunter.tracking.repository import get_discovered_jobs

    monkeypatch.setattr(
        hunt_pipeline,
        "_jobs_from_hunt",
        lambda region, depth="standard": ([], set(), set(), ScrapeStats()),
    )
    monkeypatch.setattr(hunt_pipeline, "load_cached_candidate_urls", lambda: set())
    monkeypatch.setattr(hunt_pipeline, "save_cached_candidate_urls", lambda _urls: None)

    run_id, count, _stats = hunt_pipeline.run_hunt_scrape_only("primary", tmp_path, api_config={})

    assert count == 0
    assert isinstance(run_id, str)
    assert get_discovered_jobs(tmp_path) == []


def test_load_hunt_snapshot_returns_tracker_context(tmp_path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text(
        json.dumps(
            {
                "jobs": [{"url": "https://example.com/new"}],
                "existing_urls": ["https://example.com/old"],
                "existing_titles": [],
            }
        ),
        encoding="utf-8",
    )

    jobs, existing_urls, existing_titles = hunt_pipeline.load_hunt_snapshot(path)

    assert jobs == [{"url": "https://example.com/new"}]
    assert existing_urls == {"https://example.com/old"}
    assert existing_titles == set()


def test_load_hunt_snapshot_falls_back_to_db(tmp_path) -> None:
    from job_hunter.tracking.repository import mark_urls_processed

    # Snapshot at outputs/state/ so parent.parent.parent == tmp_path (the root)
    state_dir = tmp_path / "outputs" / "state"
    state_dir.mkdir(parents=True)
    path = state_dir / "snapshot.json"
    path.write_text(json.dumps({"jobs": [{"url": "https://example.com/new"}]}), encoding="utf-8")
    mark_urls_processed(tmp_path, {"https://example.com/current"})

    _jobs, existing_urls, _existing_titles = hunt_pipeline.load_hunt_snapshot(path)

    assert existing_urls & {"https://example.com/current", "https://example.com/current/"}
