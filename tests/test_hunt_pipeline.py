from __future__ import annotations

import json

from job_hunter.pipeline import hunt as hunt_pipeline


def test_run_hunt_scrape_only_writes_snapshot_with_tracker_context(monkeypatch, tmp_path) -> None:
    jobs = [{"title": "PM", "company": "Acme", "url": "https://example.com/pm"}]
    enriched = [{**jobs[0], "snippet": "rich"}]

    monkeypatch.setattr(
        hunt_pipeline,
        "_jobs_from_hunt",
        lambda region: (jobs, {"https://example.com/old"}, set()),
    )
    monkeypatch.setattr(hunt_pipeline, "_drop_dead_urls", lambda jobs, api_cfg, checker: jobs)
    monkeypatch.setattr(hunt_pipeline, "_enrich", lambda jobs, api_cfg: enriched)

    path, count = hunt_pipeline.run_hunt_scrape_only(
        "primary",
        tmp_path,
        api_cfg={},
        url_checker=lambda *_args: True,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert count == 1
    assert path.name.endswith("_primary_candidates.json")
    assert path.parent.name == "candidates"
    assert payload["region"] == "primary"
    assert payload["count"] == 1
    assert payload["jobs"] == enriched
    assert payload["existing_urls"] == ["https://example.com/old"]
    assert payload["existing_titles"] == []


def test_run_hunt_scrape_only_writes_empty_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(hunt_pipeline, "_jobs_from_hunt", lambda region: ([], set(), set()))

    path, count = hunt_pipeline.run_hunt_scrape_only("primary", tmp_path, api_cfg={})

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert count == 0
    assert payload["count"] == 0
    assert payload["jobs"] == []


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


def test_load_hunt_snapshot_falls_back_to_current_tracker(monkeypatch, tmp_path) -> None:
    path = tmp_path / "legacy_snapshot.json"
    path.write_text(json.dumps({"jobs": [{"url": "https://example.com/new"}]}), encoding="utf-8")
    monkeypatch.setattr(
        hunt_pipeline,
        "load_processed",
        lambda: {"https://example.com/current"},
    )

    _jobs, existing_urls, existing_titles = hunt_pipeline.load_hunt_snapshot(path)

    assert existing_urls == {"https://example.com/current"}
    assert existing_titles == set()
