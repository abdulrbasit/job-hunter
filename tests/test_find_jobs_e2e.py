"""End-to-end smoke test for the find-jobs pipeline (agent mode).

Covers: scrape → candidates file → agent-context brief can read it.
All external HTTP calls are monkeypatched out.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from job_hunter import agent_context
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
        "snippet": "Drive product roadmap.",
        "source": "remotive",
        "region": "primary",
    },
]


def test_agent_mode_scrape_writes_candidates_file(monkeypatch, tmp_path: Path) -> None:
    """run_hunt_scrape_only writes to outputs/candidates/{date}_{region}_candidates.json."""
    monkeypatch.setattr(hunt_pipeline, "_jobs_from_hunt", lambda region: (_FAKE_JOBS, set(), set()))
    monkeypatch.setattr(hunt_pipeline, "_drop_dead_urls", lambda jobs, api_cfg, checker: jobs)
    monkeypatch.setattr(hunt_pipeline, "_enrich", lambda jobs, api_cfg: jobs)

    today = date.today().isoformat()
    path, count = hunt_pipeline.run_hunt_scrape_only("primary", tmp_path, api_cfg={})

    assert count == 2
    assert path.parent == tmp_path / "outputs" / "candidates"
    assert path.name == f"{today}_primary_candidates.json"
    assert path.exists()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["count"] == 2
    assert payload["region"] == "primary"
    assert len(payload["jobs"]) == 2
    assert payload["jobs"][0]["title"] == "Product Manager"


def test_agent_context_brief_reads_candidates_file(monkeypatch, tmp_path: Path) -> None:
    """After scrape, agent-context build_candidate_queue finds the candidates file."""
    monkeypatch.setattr(hunt_pipeline, "_jobs_from_hunt", lambda region: (_FAKE_JOBS, set(), set()))
    monkeypatch.setattr(hunt_pipeline, "_drop_dead_urls", lambda jobs, api_cfg, checker: jobs)
    monkeypatch.setattr(hunt_pipeline, "_enrich", lambda jobs, api_cfg: jobs)

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
    """Even with 0 results, the candidates file is written so the workflow step can read count=0."""
    monkeypatch.setattr(hunt_pipeline, "_jobs_from_hunt", lambda region: ([], set(), set()))

    path, count = hunt_pipeline.run_hunt_scrape_only("primary", tmp_path, api_cfg={})

    assert count == 0
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["count"] == 0
    assert payload["jobs"] == []
