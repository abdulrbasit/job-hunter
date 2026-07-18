from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_hunter.agent_context import (
    apply_screen_judgment,
    build_candidate_batch,
    build_candidate_queue,
    candidate_from_queue,
    candidate_lifecycle,
    discard_screened_candidates,
    final_stories_text,
    linkedin_weekly_context,
    match_stories,
    profile_context,
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


def test_candidate_queue_default_reads_from_db(tmp_path: Path) -> None:
    from job_hunter.tracking.repository import insert_jobs

    insert_jobs(
        tmp_path,
        [
            {
                "title": "Product Manager",
                "company": "TodayCo",
                "url": "https://example.com/today",
                "snippet": "Own roadmap.",
            },
            {
                "title": "Senior Product Manager",
                "company": "BacklogCo",
                "url": "https://example.com/backlog",
                "snippet": "Lead discovery.",
            },
            {
                "title": "Growth Product Manager",
                "company": "ExtraCo",
                "url": "https://example.com/extra",
                "snippet": "Growth role.",
            },
        ],
        run_id="20260630T120000Z",
    )

    queue = build_candidate_queue(root=tmp_path)

    assert queue["scope"] == "db"
    assert queue["count"] == 3
    assert queue["total_seen"] == 3


def test_candidate_queue_file_source_stays_scoped(tmp_path: Path) -> None:
    today = __import__("datetime").date.today().isoformat()
    source_file = tmp_path / "outputs" / "candidates" / f"{today}_all_candidates.json"
    _write_candidates(
        source_file,
        [{"title": "PM Today", "company": "TodayCo", "url": "https://example.com/today"}],
    )
    _write_candidates(
        tmp_path / "outputs" / "candidates" / "2026-06-02_all_candidates.json",
        [{"title": "PM Backlog", "company": "BacklogCo", "url": "https://example.com/backlog"}],
    )

    # Explicit source → file-based path, only that file is scanned
    queue = build_candidate_queue(root=tmp_path, source=source_file)

    assert queue["count"] == 1
    assert queue["jobs"][0]["company"] == "TodayCo"


def test_candidate_queue_db_skips_processed_url(tmp_path: Path) -> None:
    from job_hunter.tracking.repository import insert_jobs, mark_urls_processed

    insert_jobs(
        tmp_path,
        [
            {"title": "Processed URL", "company": "DoneCo", "url": "https://example.com/done"},
            {"title": "Unprocessed Title", "company": "TitleCo", "url": "https://example.com/title"},
        ],
        run_id="20260630T120000Z",
    )
    mark_urls_processed(tmp_path, {"https://example.com/done"})

    queue = build_candidate_queue(root=tmp_path)

    # In DB path, mark_urls_processed changes status → 'processed', so the job
    # never enters get_discovered_jobs results; count=1 proves the skip worked.
    assert queue["count"] == 1
    assert queue["source_reports"] == []


def test_candidate_queue_db_limit_applies_after_screening(tmp_path: Path) -> None:
    """A screened-out candidate must not consume the limit slot ahead of a valid one
    further down the (oldest-first) queue — regression test for the bug where `limit`
    was applied to the raw scan window before dedup/screening ran."""
    from job_hunter.tracking.repository import insert_jobs

    insert_jobs(
        tmp_path,
        [
            {
                "title": "Contract PM",
                "company": "ContractCo",
                "url": "https://example.com/contract",
                "snippet": "This is a contract role.",
            },
            {
                "title": "Full-time PM",
                "company": "RealCo",
                "url": "https://example.com/full-time",
                "snippet": "Own roadmap.",
            },
        ],
        run_id="20260630T120000Z",
    )

    queue = build_candidate_queue(root=tmp_path, limit=1)

    assert queue["count"] == 1
    assert queue["jobs"][0]["company"] == "RealCo"
    assert queue["skipped_hard_screen"] == 1


def test_candidate_queue_db_dedupes_canonical_url_variants(tmp_path: Path) -> None:
    """Two raw URLs that canonicalize to the same value must collapse to one candidate,
    even though insert_jobs already merged their DB rows — this covers the in-memory
    seen-canonicals dedup in the queue builder itself, not just the DB layer."""
    from job_hunter.tracking.repository import insert_jobs

    insert_jobs(
        tmp_path,
        [{"title": "PM", "company": "Acme", "url": "https://example.com/job-1?utm_source=a"}],
        run_id="20260630T120000Z",
    )
    insert_jobs(
        tmp_path,
        [{"title": "PM", "company": "Acme", "url": "https://example.com/job-1?utm_source=b"}],
        run_id="20260630T120000Z",
    )

    queue = build_candidate_queue(root=tmp_path)

    assert queue["count"] == 1


def test_candidate_queue_non_default_root_still_applies_exclusions(tmp_path: Path) -> None:
    """A workspace root other than the process-default one must still load and apply its
    own job_hunter.yml exclusions instead of silently screening with an empty policy."""
    from job_hunter.tracking.repository import insert_jobs

    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {
            "filters": {
                "excluded_companies": {
                    "description": "Excluded companies",
                    "entries": [{"value": "BlockedCo"}],
                }
            }
        },
    )
    insert_jobs(
        tmp_path,
        [
            {"title": "PM", "company": "BlockedCo", "url": "https://example.com/blocked"},
            {"title": "PM", "company": "GoodCo", "url": "https://example.com/good"},
        ],
        run_id="20260630T120000Z",
    )

    queue = build_candidate_queue(root=tmp_path)

    assert queue["count"] == 1
    assert queue["jobs"][0]["company"] == "GoodCo"


def test_candidate_queue_file_source_skips_db_processed_url(tmp_path: Path) -> None:
    from job_hunter.tracking.repository import mark_urls_processed

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
    mark_urls_processed(tmp_path, {"https://boards.greenhouse.io/acme/jobs/123"})

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
            "filters": {
                "languages": {"description": "Hunt languages", "entries": [{"value": "english"}]},
                "excluded_companies": {
                    "description": "Excluded companies",
                    "entries": [{"value": "Delivery Hero"}],
                },
                "excluded_titles": {
                    "description": "Excluded titles",
                    "entries": [{"value": "trainee"}],
                },
                "excluded_industries": {
                    "description": "Excluded industries",
                    "entries": [{"value": "lottery"}],
                },
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


def test_screen_candidate_batch_defers_industry_judgment(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {
            "job_titles": ["Product Manager"],
            "filters": {
                "excluded_industries": {
                    "description": "Excluded industries",
                    "entries": [{"value": "banking"}, {"value": "crypto"}],
                }
            },
        },
    )
    batch = {
        "batch_number": 1,
        "batch_size": 15,
        "jobs": [
            {
                "candidate_id": "cand_platform",
                "title": "Product Manager",
                "company": "Example SaaS",
                "snippet": "Build workflow software used by banking customers.",
            }
        ],
    }

    result = screen_candidate_batch(batch, root=tmp_path)

    assert result["skipped"] == []
    assert result["retained"][0]["candidate_id"] == "cand_platform"
    assert result["retained"][0]["judgment_signals"]["industry_terms"] == ["banking"]


def test_discard_screened_candidates_marks_every_hard_screen_skip(tmp_path: Path) -> None:
    """Regression: hard-screen skips must never depend on an agent remembering a step."""
    from job_hunter.tracking.repository import get_processed_urls, insert_jobs

    insert_jobs(
        tmp_path,
        [
            {"url": "https://example.com/keep", "title": "Product Manager", "company": "KeepCo"},
            {"url": "https://example.com/skip", "title": "Product Manager", "company": "Delivery Hero SE"},
        ],
    )
    result = {
        "retained": [{"candidate_id": "cand_keep", "url": "https://example.com/keep"}],
        "skipped": [
            {
                "candidate_id": "cand_skip",
                "url": "https://example.com/skip",
                "reasons": ["excluded_company"],
            }
        ],
    }

    discarded = discard_screened_candidates(result, root=tmp_path)

    assert discarded == 1
    assert "https://example.com/skip" in get_processed_urls(tmp_path)
    assert "https://example.com/keep" not in get_processed_urls(tmp_path)


def test_apply_screen_judgment_discards_skips_in_one_deterministic_pass(tmp_path: Path) -> None:
    """Regression: semantic screen SKIPs must be applied without a per-candidate agent loop."""
    from job_hunter.tracking.repository import get_processed_urls, insert_jobs

    insert_jobs(
        tmp_path,
        [
            {"url": "https://example.com/pass", "title": "Product Manager", "company": "SaaSCo"},
            {"url": "https://example.com/fail", "title": "Product Manager", "company": "BankCo"},
        ],
    )
    screen = {
        "retained": [
            {"candidate_id": "cand_pass", "url": "https://example.com/pass"},
            {"candidate_id": "cand_fail", "url": "https://example.com/fail"},
        ]
    }
    judgment = {
        "decisions": [
            {"candidate_id": "cand_pass", "decision": "PASS", "reason": "", "rationale": "SaaS employer."},
            {"candidate_id": "cand_fail", "decision": "SKIP", "reason": "", "rationale": "Excluded industry: banking."},
        ]
    }

    result = apply_screen_judgment(judgment, screen, root=tmp_path)

    assert result == {"discarded_count": 1, "retained_candidate_ids": ["cand_pass"]}
    assert "https://example.com/fail" in get_processed_urls(tmp_path)
    assert "https://example.com/pass" not in get_processed_urls(tmp_path)


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
    assert "job-hunter internal import-job" in payload["import_command"]


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
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    payload = candidate_lifecycle(
        root=tmp_path,
        queue=queue_path,
        index=1,
        terminal_reason="screen_skip",
        refresh_queue=queue_path,
    )

    from job_hunter.tracking.repository import get_processed_urls

    processed = get_processed_urls(tmp_path)
    refreshed = json.loads(queue_path.read_text(encoding="utf-8"))
    assert payload["action"] == "terminal_marked"
    assert any("skip" in u for u in processed)
    assert refreshed["count"] == 0


def test_candidate_lifecycle_fetch_failed_requests_webfetch(tmp_path: Path) -> None:
    job_dir = tmp_path / "outputs" / "jobs" / "job-slug"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(json.dumps({"job_description_fetch_status": "fetch_failed"}), encoding="utf-8")
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
    (job_dir / "meta.json").write_text(json.dumps({"job_description_fetch_status": "fetch_failed"}), encoding="utf-8")
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
    (job_dir / "meta.json").write_text(json.dumps({"job_description_fetch_status": "fetch_failed"}), encoding="utf-8")
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


def test_match_stories_ranks_by_jd_keyword_overlap(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {"profile": {"story_bank": "profile/story_bank.md"}},
    )
    story_bank = tmp_path / "profile" / "story_bank.md"
    story_bank.parent.mkdir(parents=True)
    story_bank.write_text(
        """# Role One

## Final -- refined STAR stories

### FN-01 - Kubernetes migration
**Rating: 9/10**
Situation: led a kubernetes and terraform infrastructure migration.
- **Tags:** kubernetes, terraform, infrastructure

### FN-02 - Unrelated story
**Rating: 8/10**
Situation: organized a company offsite event.
- **Tags:** events
""",
        encoding="utf-8",
    )
    job_dir = tmp_path / "outputs" / "jobs" / "job-slug"
    job_dir.mkdir(parents=True)
    (job_dir / "jd.md").write_text("We need kubernetes and terraform infrastructure expertise.", encoding="utf-8")

    ranked = match_stories(job="job-slug", root=tmp_path)

    assert ranked[0]["id"] == "FN-01"
    assert ranked[0]["score"] > 0
    assert "kubernetes" in ranked[0]["matched_terms"]
    assert all(r["id"] != "FN-02" for r in ranked)


def test_match_stories_returns_empty_without_story_bank_or_jd(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "job_hunter.yml", {"profile": {}})

    assert match_stories(job="no-such-job", root=tmp_path) == []


def test_score_context_full_is_bounded_and_includes_story_index(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {
            "scoring": {"min_fit_score": 70, "max_years_experience_required": 5},
            "job_titles": ["Product Manager"],
            "filters": {"excluded_industries": ["aerospace_defense"]},
            "profile": {
                "resume_tex": "profile/resume_double_column.tex",
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
    (tmp_path / "profile" / "resume_double_column.tex").write_text(
        "\\documentclass{altacv}\nVerified resume evidence.",
        encoding="utf-8",
    )
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
    assert "Verified resume evidence." in payload["profile"]["resume_tex"]
    assert payload["profile"]["target_titles"] == ["Product Manager"]
    assert payload["profile"]["excluded_industries"] == ["aerospace_defense"]
    assert payload["story_index"][0]["id"] == "ST-01"
    assert payload["matched_stories"] == []
    assert "APPLY" in " ".join(payload["decision_rules"])
    assert any(o["path"] == "outputs/jobs/job-slug/score.yml" for o in payload["required_outputs"])
    assert any(o["path"] == "outputs/jobs/job-slug/evaluation.md" for o in payload["required_outputs"])


def test_score_context_omits_profile_when_not_included(tmp_path: Path) -> None:
    """Batch scoring fetches the profile once via profile_context(), then passes
    include_profile=False per job — the payload must not re-embed the profile bytes."""
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {"scoring": {}, "job_titles": [], "profile": {}},
    )
    job_dir = tmp_path / "outputs" / "jobs" / "job-slug"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(json.dumps({"company": "ExampleCo"}), encoding="utf-8")
    (job_dir / "jd.md").write_text("JD text", encoding="utf-8")
    _write_yaml(job_dir / "score.yml", {"status": "pending"})
    (tmp_path / "profile").mkdir(exist_ok=True)
    (tmp_path / "profile" / "career_context.md").write_text("Prefers concise cover letters.", encoding="utf-8")

    payload = score_context(mode="full", root=tmp_path, job="job-slug", include_profile=False)

    assert isinstance(payload["profile"], str)
    assert "Prefers concise cover letters." not in payload["profile"]
    assert payload["job"]["meta"]["company"] == "ExampleCo"


def test_profile_context_matches_score_context_full_profile_block(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {"scoring": {}, "job_titles": ["Product Manager"], "profile": {}},
    )
    (tmp_path / "profile").mkdir(exist_ok=True)
    (tmp_path / "profile" / "career_context.md").write_text("Prefers concise cover letters.", encoding="utf-8")

    standalone = profile_context(tmp_path)

    assert standalone["career_context"] == "Prefers concise cover letters."
    assert standalone["target_titles"] == ["Product Manager"]


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


def test_score_context_resolves_max_years_from_experience_levels_when_unset(tmp_path: Path) -> None:
    """Regression: the agent scoring context used to pass the raw (often absent)
    scoring.max_years_experience_required straight through — a workspace with no
    explicit override showed the agent `null` instead of the selected experience_levels'
    own derived cap."""
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        json.dumps({"jobs": [{"title": "PM", "company": "ExampleCo", "snippet": "short"}]}),
        encoding="utf-8",
    )
    _write_yaml(
        tmp_path / "config" / "job_hunter.yml",
        {"scoring": {}, "job_titles": [], "profile": {}, "filters": {"experience_levels": ["entry", "junior"]}},
    )

    payload = score_context(mode="snippet", root=tmp_path, queue=queue_path)

    assert payload["profile"]["scoring"]["max_years_experience_required"] == 2


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


def test_agent_context_modules_never_call_the_llm_directly() -> None:
    """Agent mode's Python side prepares context deterministically; the agent skill makes
    the actual LLM call, not job_hunter.agent_context. A direct llm/ import here would mean
    Python is calling the LLM behind the agent's back."""
    import ast

    package_dir = Path(__file__).resolve().parents[1] / "job_hunter" / "agent_context"
    for py_file in package_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    assert not module.startswith("job_hunter.llm"), f"{py_file.name} imports {module}"
                continue
            if module:
                assert not module.startswith("job_hunter.llm"), f"{py_file.name} imports {module}"
