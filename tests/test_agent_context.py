from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from job_hunter.agent_context import (
    build_candidate_batch,
    build_candidate_queue,
    candidate_from_queue,
    candidate_lifecycle,
    final_stories_text,
    linkedin_weekly_context,
    llm_search_config,
    score_context,
    screen_candidate_batch,
    story_by_id,
    story_index,
    validate_score_file,
)


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def _write_candidates(path: Path, jobs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


def test_candidate_queue_bounds_large_snapshot(tmp_path: Path) -> None:
    candidate_file = tmp_path / "outputs" / "candidates" / "2026-05-31_all_candidates.json"
    candidate_file.parent.mkdir(parents=True)
    huge_snippet = "important requirement " * 500
    candidate_file.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "title": "Product Manager",
                        "company": "ExampleCo",
                        "url": "https://example.com/job-1",
                        "snippet": huge_snippet,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    queue = build_candidate_queue(root=tmp_path, source=candidate_file, max_snippet_chars=120)

    assert queue["count"] == 1
    assert queue["total_seen"] == 1
    assert len(queue["jobs"][0]["snippet"]) <= 120
    assert huge_snippet not in json.dumps(queue)


def test_candidate_queue_assigns_stable_candidate_ids(tmp_path: Path) -> None:
    candidate_file = tmp_path / "outputs" / "candidates" / "2026-06-01_all_candidates.json"
    _write_candidates(
        candidate_file,
        [
            {
                "title": "Product Manager",
                "company": "ExampleCo",
                "url": "https://example.com/job-1",
            }
        ],
    )

    first = build_candidate_queue(root=tmp_path, source=candidate_file)
    second = build_candidate_queue(root=tmp_path, source=candidate_file)

    assert first["jobs"][0]["candidate_id"].startswith("cand_")
    assert first["jobs"][0]["candidate_id"] == second["jobs"][0]["candidate_id"]
    assert first["jobs"][0]["queue_index"] == 1


def test_candidate_queue_default_matches_briefing_backlog_scope(tmp_path: Path) -> None:
    today = __import__("datetime").date.today().isoformat()
    _write_candidates(
        tmp_path / "outputs" / "candidates" / f"{today}_vancouver_candidates.json",
        [
            {
                "title": "Product Manager",
                "company": "TodayCo",
                "url": "https://example.com/today",
                "snippet": "Own roadmap and delivery.",
            }
        ],
    )
    _write_candidates(
        tmp_path / "outputs" / "candidates" / "2026-06-02_all_candidates.json",
        [
            {
                "title": "Senior Product Manager",
                "company": "BacklogCo",
                "url": "https://example.com/backlog",
                "snippet": "Lead discovery and analytics.",
            }
        ],
    )
    _write_candidates(
        tmp_path / "outputs" / "candidates" / "2026-06-02_llm_search_candidates.json",
        [
            {
                "title": "AI Product Manager",
                "company": "LLMCo",
                "url": "https://example.com/llm",
                "snippet": "AI product role with prioritization.",
            }
        ],
    )

    queue = build_candidate_queue(root=tmp_path)

    assert queue["scope"] == "briefing-backlog"
    assert queue["count"] == 3
    assert queue["total_seen"] == 3
    assert {job["source_file"] for job in queue["jobs"]} == {
        f"{today}_vancouver_candidates.json",
        "2026-06-02_all_candidates.json",
        "2026-06-02_llm_search_candidates.json",
    }


def test_candidate_queue_today_scope_stays_narrow(tmp_path: Path) -> None:
    today = __import__("datetime").date.today().isoformat()
    _write_candidates(
        tmp_path / "outputs" / "candidates" / f"{today}_all_candidates.json",
        [
            {
                "title": "PM Today",
                "company": "TodayCo",
                "url": "https://example.com/today",
            }
        ],
    )
    _write_candidates(
        tmp_path / "outputs" / "candidates" / "2026-06-02_all_candidates.json",
        [
            {
                "title": "PM Backlog",
                "company": "BacklogCo",
                "url": "https://example.com/backlog",
            }
        ],
    )

    queue = build_candidate_queue(root=tmp_path, scope="today")

    assert queue["scope"] == "today"
    assert queue["count"] == 1
    assert queue["jobs"][0]["company"] == "TodayCo"


def test_candidate_queue_metadata_explains_zero_contribution_files(
    tmp_path: Path,
) -> None:
    _write_candidates(
        tmp_path / "outputs" / "candidates" / "2026-06-02_all_candidates.json",
        [
            {
                "title": "Processed URL",
                "company": "DoneCo",
                "url": "https://example.com/done",
            },
            {
                "title": "Unprocessed Title",
                "company": "TitleCo",
                "url": "https://example.com/title",
            },
        ],
    )
    _write_yaml(
        tmp_path / "outputs" / "state" / "discovered_urls.yml",
        {
            "discovered": ["https://example.com/done"],
        },
    )

    queue = build_candidate_queue(root=tmp_path)

    assert queue["count"] == 1
    assert queue["skipped_processed"] == 1
    assert queue["source_reports"] == [
        {
            "file": "2026-06-02_all_candidates.json",
            "path": (tmp_path / "outputs" / "candidates" / "2026-06-02_all_candidates.json").as_posix(),
            "total_seen": 2,
            "queued": 1,
            "skipped_processed_url": 1,
            "skipped_duplicate_url": 0,
            "skipped_duplicate_title": 0,
            "reason": "",
        }
    ]


def test_morning_briefing_uses_same_backlog_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import job_hunter.briefing as briefing

    today = __import__("datetime").date.today().isoformat()
    _write_candidates(
        tmp_path / "outputs" / "candidates" / f"{today}_all_candidates.json",
        [
            {
                "title": "PM Today",
                "company": "TodayCo",
                "url": "https://example.com/today",
            }
        ],
    )
    _write_candidates(
        tmp_path / "outputs" / "candidates" / "2026-06-02_llm_search_candidates.json",
        [
            {
                "title": "PM Backlog",
                "company": "BacklogCo",
                "url": "https://example.com/backlog",
            }
        ],
    )
    _write_yaml(
        tmp_path / "outputs" / "state" / "discovered_urls.yml",
        {"discovered": []},
    )

    monkeypatch.setattr(briefing, "repo_path", lambda *parts: tmp_path.joinpath(*parts))

    text = briefing.build_briefing()

    assert f"`{today}_all_candidates.json`" in text
    assert "`2026-06-02_llm_search_candidates.json`" in text
    assert "**2 unprocessed candidate(s) across 2 active file(s).**" in text
    assert "score and tailor backlog candidates" in text


def test_morning_briefing_hides_processed_candidate_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import job_hunter.briefing as briefing

    today = __import__("datetime").date.today().isoformat()
    _write_candidates(
        tmp_path / "outputs" / "candidates" / f"{today}_active_candidates.json",
        [
            {
                "title": "PM Active",
                "company": "ActiveCo",
                "url": "https://example.com/active",
            }
        ],
    )
    _write_candidates(
        tmp_path / "outputs" / "candidates" / f"{today}_processed_candidates.json",
        [
            {
                "title": "PM Done",
                "company": "DoneCo",
                "url": "https://example.com/done",
            }
        ],
    )
    _write_yaml(
        tmp_path / "outputs" / "state" / "discovered_urls.yml",
        {"discovered": ["https://example.com/done"]},
    )
    monkeypatch.setattr(briefing, "repo_path", lambda *parts: tmp_path.joinpath(*parts))

    text = briefing.build_briefing()

    assert "`" + f"{today}_active_candidates.json" + "`" in text
    assert f"{today}_processed_candidates.json" not in text
    assert "Hidden from brief: 1 processed/duplicate file(s)." in text


def test_candidate_queue_skips_processed_title_variants(tmp_path: Path) -> None:
    candidate_file = tmp_path / "outputs" / "candidates" / "2026-06-01_all_candidates.json"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "title": "Job Application for Product Owner at Acme",
                        "company": "Acme",
                        "url": "https://boards.greenhouse.io/acme/jobs/123",
                        "snippet": "Current openings",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_yaml(
        tmp_path / "outputs" / "state" / "discovered_urls.yml",
        {"discovered": ["https://boards.greenhouse.io/acme/jobs/123"]},
    )

    queue = build_candidate_queue(root=tmp_path, source=candidate_file)

    assert queue["count"] == 0
    assert queue["total_seen"] == 1
    assert queue["skipped_processed"] == 1


def test_candidate_from_queue_returns_one_item(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {"queue_index": 1, "title": "PM"},
                    {"queue_index": 2, "title": "PO"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert candidate_from_queue(queue_path, 2)["title"] == "PO"


def test_candidate_from_queue_returns_item_by_candidate_id_after_reindex(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {"candidate_id": "cand_a", "queue_index": 1, "title": "A"},
                    {"candidate_id": "cand_b", "queue_index": 1, "title": "B"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert candidate_from_queue(queue_path, 1, candidate_id="cand_b")["title"] == "B"


def test_candidate_batch_freezes_first_15_candidates(tmp_path: Path) -> None:
    queue = {"jobs": [{"candidate_id": f"cand_{i}"} for i in range(20)]}

    batch = build_candidate_batch(queue)

    assert batch["batch_size"] == 15
    assert batch["count"] == 15
    assert batch["jobs"][-1]["candidate_id"] == "cand_14"


def test_screen_candidate_batch_filters_exclusions_and_duplicates(
    tmp_path: Path,
) -> None:
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {
            "job_titles": ["Product Manager"],
            "regions": {"berlin": {"location": "Berlin"}},
            "exclusions": {
                "companies": ["Delivery Hero"],
                "title_terms": ["trainee"],
                "industries": ["lottery"],
                "languages": ["german"],
            },
        },
    )
    prior = tmp_path / "outputs" / "jobs" / "old"
    prior.mkdir(parents=True)
    (prior / "meta.json").write_text(
        json.dumps({"company": "PriorCo", "title": "Product Manager"}),
        encoding="utf-8",
    )
    batch = {
        "batch_number": 1,
        "batch_size": 15,
        "jobs": [
            {
                "candidate_id": "cand_keep",
                "title": "Product Manager",
                "company": "KeepCo",
                "region": "berlin",
                "location": "Berlin",
                "snippet": "Own roadmap.",
            },
            {
                "candidate_id": "cand_excluded",
                "title": "Product Manager",
                "company": "Delivery Hero SE",
                "region": "berlin",
                "location": "Berlin",
                "snippet": "Own roadmap.",
            },
            {
                "candidate_id": "cand_dup",
                "title": "Product Manager",
                "company": "PriorCo",
                "region": "berlin",
                "location": "Berlin",
                "snippet": "Own roadmap.",
            },
        ],
    }

    result = screen_candidate_batch(batch, root=tmp_path)

    assert [row["candidate_id"] for row in result["retained"]] == ["cand_keep"]
    skipped = {row["candidate_id"]: row["reasons"] for row in result["skipped"]}
    assert "excluded_company" in skipped["cand_excluded"]
    assert "duplicate_application" in skipped["cand_dup"]


def test_candidate_lifecycle_routes_thin_candidate_to_import(tmp_path: Path) -> None:
    queue_path = tmp_path / "outputs" / "state" / "queue.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "title": "Product Manager",
                        "company": "ThinCo",
                        "url": "https://example.com/thin",
                        "jd_status": "thin",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = candidate_lifecycle(root=tmp_path, queue=queue_path, index=1)

    assert payload["action"] == "import_required"
    assert payload["reason"] == "candidate_jd_status:thin"
    assert "job-hunter import-job" in payload["import_command"]


def test_candidate_lifecycle_uses_candidate_id_in_commands(tmp_path: Path) -> None:
    queue_path = tmp_path / "outputs" / "state" / "queue.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "candidate_id": "cand_a",
                        "title": "Product Manager",
                        "company": "ThinCo",
                        "url": "https://example.com/thin",
                        "jd_status": "thin",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = candidate_lifecycle(root=tmp_path, queue=queue_path, candidate_id="cand_a")

    assert "--candidate-id cand_a" in payload["import_command"]


def test_candidate_lifecycle_marks_terminal_and_refreshes_queue(tmp_path: Path) -> None:
    candidate_file = (
        tmp_path / "outputs" / "candidates" / f"{__import__('datetime').date.today().isoformat()}_candidates.json"
    )
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "title": "Product Manager",
                        "company": "SkipCo",
                        "url": "https://example.com/skip",
                        "snippet": "A short snippet.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    queue_path = tmp_path / "outputs" / "state" / "agent_candidate_queue.json"
    queue = build_candidate_queue(root=tmp_path, source=candidate_file)
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    payload = candidate_lifecycle(
        root=tmp_path,
        queue=queue_path,
        index=1,
        terminal_reason="screen_skip",
        refresh_queue=queue_path,
    )

    processed = yaml.safe_load((tmp_path / "outputs" / "state" / "discovered_urls.yml").read_text(encoding="utf-8"))
    refreshed = json.loads(queue_path.read_text(encoding="utf-8"))
    assert payload["action"] == "terminal_marked"
    assert processed["discovered"] == ["https://example.com/skip"]
    assert "applied_titles" not in processed
    assert refreshed["count"] == 0


def test_candidate_lifecycle_fetch_failed_requests_webfetch(tmp_path: Path) -> None:
    job_dir = tmp_path / "outputs" / "jobs" / "job-slug"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(json.dumps({"fetch_status": "fetch_failed"}), encoding="utf-8")
    (job_dir / "jd.md").write_text("Paste the job description here.", encoding="utf-8")
    _write_yaml(job_dir / "score.yml", {"status": "pending"})

    payload = candidate_lifecycle(root=tmp_path, job="job-slug")

    assert payload["action"] == "webfetch_required"
    assert payload["reason"] == "job_fetch_failed"


def test_candidate_lifecycle_fetch_failed_accepts_full_fallback_text(
    tmp_path: Path,
) -> None:
    job_dir = tmp_path / "outputs" / "jobs" / "job-slug"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(json.dumps({"fetch_status": "fetch_failed"}), encoding="utf-8")
    (job_dir / "jd.md").write_text("Paste the job description here.", encoding="utf-8")
    _write_yaml(job_dir / "score.yml", {"status": "pending"})

    fallback = (
        "About the role\nWe need a Product Manager to own roadmap and discovery. "
        "Responsibilities include prioritization, stakeholder alignment, and delivery. "
        "Requirements include product management experience, analytics, and communication. "
    ) * 8

    payload = candidate_lifecycle(root=tmp_path, job="job-slug", fallback_text=fallback)

    assert payload["action"] == "reimport_with_fallback"
    assert payload["fallback_text_status"] == "full"


def test_candidate_lifecycle_rejects_non_full_fallback_text(tmp_path: Path) -> None:
    job_dir = tmp_path / "outputs" / "jobs" / "job-slug"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(json.dumps({"fetch_status": "fetch_failed"}), encoding="utf-8")
    (job_dir / "jd.md").write_text("Paste the job description here.", encoding="utf-8")
    _write_yaml(job_dir / "score.yml", {"status": "pending"})

    payload = candidate_lifecycle(root=tmp_path, job="job-slug", fallback_text="Current openings")

    assert payload["action"] == "terminal_candidate"
    assert payload["reason"] == "fallback_text_not_full_jd"


def test_story_index_and_story_by_id_use_final_stories_only(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {"profile": {"story_bank": "profile/story_bank.md"}},
    )
    story_bank = tmp_path / "profile" / "story_bank.md"
    story_bank.parent.mkdir(parents=True)
    story_bank.write_text(
        """# Role One

## Draft -- raw notes

### DR-01 - Draft story
**Rating: 10/10**

## Final -- refined STAR stories

### FN-01 - Final story
**Rating: 9/10**
Situation: shipped a verified product outcome.
- **Tags:** product, delivery
""",
        encoding="utf-8",
    )

    index = story_index(root=tmp_path)

    assert [story["id"] for story in index] == ["FN-01"]
    assert index[0]["tags"] == ["product", "delivery"]
    assert story_by_id("FN-01", root=tmp_path).title == "Final story"
    assert story_by_id("DR-01", root=tmp_path) is None

    final_text = final_stories_text(root=tmp_path)
    assert "FN-01" in final_text
    assert "DR-01" not in final_text
    assert "Draft -- raw notes" not in final_text


def test_score_context_full_is_bounded_and_includes_story_index(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {
            "scoring": {"min_fit_score": 70, "max_years_experience_required": 5},
            "job_titles": ["Product Manager"],
            "profile": {
                "story_bank": "profile/story_bank.md",
                "career_context": "profile/career_context.md",
            },
        },
    )
    job_dir = tmp_path / "outputs" / "jobs" / "job-slug"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps({"company": "ExampleCo", "title": "Product Manager"}),
        encoding="utf-8",
    )
    (job_dir / "jd.md").write_text("JD " + ("requirement " * 200), encoding="utf-8")
    _write_yaml(job_dir / "score.yml", {"status": "pending"})
    (tmp_path / "profile").mkdir(exist_ok=True)
    (tmp_path / "profile" / "career_context.md").write_text("Prefers concise cover letters.", encoding="utf-8")
    (tmp_path / "profile" / "story_bank.md").write_text(
        """# Role

## Final -- refined STAR stories

### ST-01 - Strong story
**Rating: 8/10**
Situation: relevant verified work.
- **Tags:** product
""",
        encoding="utf-8",
    )

    payload = score_context(mode="full", root=tmp_path, job="job-slug", max_jd_chars=90)

    assert payload["job"]["meta"]["company"] == "ExampleCo"
    assert len(payload["job"]["jd_excerpt"]) <= 90
    assert payload["profile"]["career_context"] == "Prefers concise cover letters."
    assert payload["profile"]["target_titles"] == ["Product Manager"]
    assert payload["story_index"][0]["id"] == "ST-01"


def test_score_context_snippet_uses_no_story_bank(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        json.dumps({"jobs": [{"title": "PM", "company": "ExampleCo", "snippet": "short"}]}),
        encoding="utf-8",
    )
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {"scoring": {}, "job_titles": [], "profile": {}},
    )

    payload = score_context(mode="snippet", root=tmp_path, queue=queue_path)

    assert payload["candidate"]["company"] == "ExampleCo"
    assert payload["story_index"] == []


def test_llm_search_config_returns_region_title_exclusion_context(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {
            "regions": {
                "berlin": {
                    "enabled": True,
                    "primary": True,
                    "country": "DE",
                    "search_lang": "en",
                    "location": "Berlin",
                    "job_titles": ["Product Owner"],
                },
                "remote_de": {
                    "enabled": True,
                    "country": "DE",
                    "location": "remote Germany",
                },
                "disabled": {
                    "enabled": False,
                    "country": "US",
                    "location": "New York",
                    "job_titles": ["Growth PM"],
                },
            },
            "job_titles": ["Product Manager", "Technical Product Manager"],
            "search": {
                "llm_search": {
                    "enabled": True,
                    "trigger_threshold": 3,
                    "max_results_per_run": 9,
                },
            },
            "exclusions": {
                "companies": ["NopeCo"],
                "title_terms": ["engineer"],
                "languages": ["german"],
            },
            "scoring": {"batch_size": 7},
        },
    )

    payload = llm_search_config(root=tmp_path)
    payload_text = json.dumps(payload)

    assert payload["enabled"] is True
    assert payload["trigger_threshold"] == 3
    assert payload["max_results_per_run"] == 9
    assert payload["batch_size"] == 7
    assert payload["searches_per_title_per_region"] == 5
    assert [region["region"] for region in payload["regions"]] == ["berlin", "remote_de"]
    assert payload["regions"][0]["job_titles"] == ["Product Owner"]
    assert payload["regions"][1]["job_titles"] == [
        "Product Manager",
        "Technical Product Manager",
    ]
    assert payload["exclusions"]["excluded_companies"] == ["NopeCo"]
    assert payload["exclusions"]["excluded_title_terms"] == ["engineer"]
    assert all("companies" not in region for region in payload["regions"])
    assert "career_url" not in payload_text
    assert "Should Not Leak" not in payload_text


def test_linkedin_weekly_limit_comes_from_job_hunter_config(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {"scoring": {"batch_size": 2}},
    )
    jobs_dir = tmp_path / "outputs" / "jobs"
    for i in range(5):
        job_dir = jobs_dir / f"job-{i}"
        job_dir.mkdir(parents=True)
        (job_dir / "meta.json").write_text(
            json.dumps({"company": f"Co {i}", "title": "Product Manager"}),
            encoding="utf-8",
        )
        _write_yaml(
            job_dir / "score.yml",
            {
                "score": 80,
                "decision": "APPLY",
                "role_summary": "Product role.",
                "score_rationale": "Strong match.",
                "recommendation": "Apply.",
                "matched_story_ids": ["ST-01"],
                "matched": ["roadmap"],
                "gaps": [],
            },
        )

    payload = linkedin_weekly_context(root=tmp_path, days=1)

    assert payload["job_limit"] == 2
    assert payload["job_limit_source"] == "config:scoring.batch_size * days"
    assert len(payload["jobs"]) == 2


def test_validate_score_file_requires_utf8_yaml_schema(tmp_path: Path) -> None:
    score_path = tmp_path / "score.yml"
    _write_yaml(
        score_path,
        {
            "score": 80,
            "decision": "APPLY",
            "role_summary": "Product role.",
            "score_rationale": "Strong match.",
            "recommendation": "Apply.",
            "matched_story_ids": ["ST-01"],
            "matched": ["roadmap"],
            "gaps": [],
        },
    )

    assert validate_score_file(score_path)["valid"]

    score_path.write_bytes(b"score: 80\nmatched: \x97\n")

    assert not validate_score_file(score_path)["valid"]
