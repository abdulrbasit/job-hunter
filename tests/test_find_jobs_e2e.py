"""End-to-end smoke test for the find-jobs pipeline (agent mode).

Covers: scrape → candidates file → agent-context brief can read it.
All external HTTP calls are monkeypatched out.
"""

from __future__ import annotations

from pathlib import Path

from job_hunter import agent_context
from job_hunter.models import ScrapeStats
from job_hunter.pipeline import hunt as hunt_pipeline

_FAKE_JOBS = [
    {
        "title": "Product Manager",
        "company": "Acme",
        "url": "https://acme.example.com/jobs/pm",
        "location": "Berlin",
        "snippet": "Lead product strategy.",
        "source": "himalayas",
        "region": "primary",
    },
    {
        "title": "Senior PM",
        "company": "Beta Corp",
        "url": "https://beta.example.com/jobs/spm",
        "location": "Remote",
        "location_restrictions": ["Germany"],
        "snippet": "Drive product roadmap.",
        "source": "remotive",
        "region": "primary",
    },
]


def test_agent_mode_scrape_writes_candidates_file(monkeypatch, tmp_path: Path) -> None:
    """run_hunt_scrape_only inserts jobs into DB and returns (run_id, count, stats)."""
    from job_hunter.db.jobs import get_discovered_jobs

    monkeypatch.setattr(
        hunt_pipeline,
        "_jobs_from_hunt",
        lambda region, depth="standard": (
            _FAKE_JOBS,
            set(),
            set(),
            ScrapeStats(total_fetched=2, total_after_policy=2),
        ),
    )
    monkeypatch.setattr(hunt_pipeline, "_drop_dead_urls", lambda jobs, api_cfg, checker: jobs)
    monkeypatch.setattr(hunt_pipeline, "_enrich", lambda jobs, api_cfg: jobs)
    monkeypatch.setattr(hunt_pipeline, "load_cached_candidate_urls", lambda: set())
    monkeypatch.setattr(hunt_pipeline, "save_cached_candidate_urls", lambda _urls: None)

    run_id, count, _stats = hunt_pipeline.run_hunt_scrape_only("primary", tmp_path, api_cfg={})

    assert count == 2
    assert isinstance(run_id, str) and "T" in run_id
    jobs = get_discovered_jobs(tmp_path, run_id=run_id)
    assert len(jobs) == 2
    titles = {j["title"] for j in jobs}
    assert "Product Manager" in titles


def test_agent_context_brief_reads_candidates_file(monkeypatch, tmp_path: Path) -> None:
    """After scrape, agent-context build_candidate_queue finds the candidates file."""
    monkeypatch.setattr(
        hunt_pipeline,
        "_jobs_from_hunt",
        lambda region, depth="standard": (
            _FAKE_JOBS,
            set(),
            set(),
            ScrapeStats(total_fetched=2, total_after_policy=2),
        ),
    )
    monkeypatch.setattr(hunt_pipeline, "_drop_dead_urls", lambda jobs, api_cfg, checker: jobs)
    monkeypatch.setattr(hunt_pipeline, "_enrich", lambda jobs, api_cfg: jobs)
    monkeypatch.setattr(hunt_pipeline, "load_cached_candidate_urls", lambda: set())
    monkeypatch.setattr(hunt_pipeline, "save_cached_candidate_urls", lambda _urls: None)

    # Set up state file expected by _load_processed_for_root
    state_dir = tmp_path / "outputs" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "discovered_urls.yml").write_text("discovered: []\n", encoding="utf-8")

    hunt_pipeline.run_hunt_scrape_only("primary", tmp_path, api_cfg={})

    queue = agent_context.build_candidate_queue(root=tmp_path, today_only=False, limit=100)
    assert queue["count"] == 2
    ids = [c["candidate_id"] for c in queue["jobs"]]
    assert len(ids) == len(set(ids)), "candidate_ids must be unique"


def test_agent_mode_empty_scrape_writes_zero_count_file(monkeypatch, tmp_path: Path) -> None:
    """Even with 0 results, run_hunt_scrape_only returns count=0 and run_id string."""
    from job_hunter.db.jobs import get_discovered_jobs

    monkeypatch.setattr(
        hunt_pipeline,
        "_jobs_from_hunt",
        lambda region, depth="standard": ([], set(), set(), ScrapeStats()),
    )
    monkeypatch.setattr(hunt_pipeline, "load_cached_candidate_urls", lambda: set())
    monkeypatch.setattr(hunt_pipeline, "save_cached_candidate_urls", lambda _urls: None)

    run_id, count, _stats = hunt_pipeline.run_hunt_scrape_only("primary", tmp_path, api_cfg={})

    assert count == 0
    assert isinstance(run_id, str)
    assert get_discovered_jobs(tmp_path) == []
