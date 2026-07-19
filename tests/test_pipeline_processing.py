"""Tests for pipeline/stages/processing.py — batch processing and README updates."""

from unittest.mock import patch

from job_hunter.pipeline.stages import processing


def _match(idx: int) -> dict:
    return {
        "score": idx,
        "matched_keywords": [],
        "gaps": [],
        "job": {
            "title": f"Product Manager {idx}",
            "company": "TestCo",
            "url": f"https://example.com/jobs/{idx}",
            "snippet": "Product role.",
        },
    }


def test_process_jobs_caps_tailoring_to_configured_batch_size() -> None:
    jobs = [_match(idx)["job"] for idx in range(20)]
    matches = [_match(idx) for idx in range(20)]
    processed_titles = []

    def fake_process(match) -> bool:
        processed_titles.append(match["job"]["title"])
        return True

    with (
        patch("job_hunter.pipeline.stages.processing.score_and_filter_jobs", return_value=matches),
        patch("job_hunter.pipeline.stages.processing._process_match", side_effect=fake_process),
    ):
        processed = processing.process_jobs(
            jobs,
            skip_validate=True,
            skip_score=False,
            max_years=4,
            api_config={},
            scoring_config={"scoring": {"batch_size": 7}},
        )

    assert len(processed) == 7
    assert processed_titles == [f"Product Manager {idx}" for idx in range(19, 12, -1)]


def test_process_jobs_uses_default_batch_size_when_config_missing() -> None:
    jobs = [_match(idx)["job"] for idx in range(20)]
    processed_titles = []

    def fake_process(match) -> bool:
        processed_titles.append(match["job"]["title"])
        return True

    with patch("job_hunter.pipeline.stages.processing._process_match", side_effect=fake_process):
        processed = processing.process_jobs(
            jobs,
            skip_validate=True,
            skip_score=True,
            max_years=4,
            api_config={},
            scoring_config={"scoring": {}},
        )

    assert len(processed) == 15
    assert processed_titles == [f"Product Manager {idx}" for idx in range(15)]


def test_make_generated_tex_self_contained_uses_local_asset_names(tmp_path) -> None:
    image = tmp_path / "Profile-2025.png"
    image.write_bytes(b"image")
    cls = tmp_path / "altacv.cls"
    cls.write_text("class", encoding="utf-8")
    tex = "\n".join(
        [
            r"\documentclass[9pt,a4paper,ragged2e,withhyper]{../../altacv}",
            r"\photoR{2.8cm}{../../Profile-2025}",
            r"\begin{document}",
            r"\end{document}",
        ]
    )

    def fake_profile_path(key, default):
        return image if key == "profile_image" else cls

    with patch("job_hunter.pipeline.stages.processing.profile_path", side_effect=fake_profile_path):
        portable = processing._make_generated_tex_self_contained(tex)

    assert r"\documentclass[9pt,a4paper,ragged2e,withhyper]{altacv}" in portable
    assert r"\photoR{2.8cm}{Profile-2025}" in portable


def test_copy_latex_assets_places_dependencies_in_job_dir(tmp_path) -> None:
    job_dir = tmp_path / "jobs" / "example"
    job_dir.mkdir(parents=True)
    image = tmp_path / "Profile-2025.png"
    image.write_bytes(b"image")
    cls = tmp_path / "altacv.cls"
    cls.write_text("class", encoding="utf-8")

    def fake_profile_path(key, default):
        return image if key == "profile_image" else cls

    with patch("job_hunter.pipeline.stages.processing.profile_path", side_effect=fake_profile_path):
        processing._copy_latex_assets(job_dir)

    assert (job_dir / "Profile-2025.png").read_bytes() == b"image"
    assert (job_dir / "altacv.cls").read_text(encoding="utf-8") == "class"


def test_update_readme_includes_location_and_migrates_existing_rows(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "<!-- JOBS_TABLE_START -->",
                "| Date | Job | Score | Files |",
                "|---|---|---|---|",
                "| 2026-05-01 | [Old PM @ OldCo](https://example.com/old) | 72 | [Files](jobs/old/) |",
                "<!-- JOBS_TABLE_END -->",
            ]
        ),
        encoding="utf-8",
    )
    match = {
        "score": 88,
        "job": {
            "title": "Product | Manager",
            "company": "TestCo",
            "location": "Dublin, Ireland",
            "url": "https://example.com/jobs/pm",
        },
    }

    with (
        patch("job_hunter.pipeline.stages.processing.ROOT", str(tmp_path)),
        patch("job_hunter.pipeline.stages.processing._today", return_value="2026-05-19"),
    ):
        processing.update_readme([match])

    content = readme.read_text(encoding="utf-8")
    assert "| Date | Job | Location | Score | Files |" in content
    assert "**Application stats:** 2 jobs tracked since 2026-05-01 (3 weeks)." in content
    assert (
        "| 2026-05-19 | [Product \\| Manager @ TestCo](https://example.com/jobs/pm) | Dublin, Ireland | 88 |" in content
    )
    assert "| 2026-05-01 | [Old PM @ OldCo](https://example.com/old) | Unknown | 72 |" in content


def test_update_readme_refreshes_existing_score(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "<!-- JOBS_TABLE_START -->",
                "| Date | Job | Location | Score | Files |",
                "|---|---|---|---|---|",
                "| 2026-06-12 | [Product Manager @ Acme](https://example.com/acme) | Berlin | 0 | [Files](jobs/old/) |",
                "<!-- JOBS_TABLE_END -->",
            ]
        ),
        encoding="utf-8",
    )
    match = {
        "score": 88,
        "job": {
            "title": "Product Manager",
            "company": "Acme",
            "location": "Berlin",
            "url": "https://example.com/acme",
        },
    }

    with (
        patch("job_hunter.pipeline.stages.processing.ROOT", str(tmp_path)),
        patch("job_hunter.pipeline.stages.processing._today", return_value="2026-06-12"),
    ):
        processing.update_readme([match])

    content = readme.read_text(encoding="utf-8")
    assert "| 88 |" in content
    assert "| 0 |" not in content


def test_update_readme_refreshes_existing_stats_block(tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "## Applied Jobs",
                "<!-- JOBS_STATS_START -->",
                "**Application stats:** stale",
                "<!-- JOBS_STATS_END -->",
                "",
                "<!-- JOBS_TABLE_START -->",
                "| Date | Job | Location | Score | Files |",
                "|---|---|---|---|---|",
                "| 2026-05-05 | [PM @ OldCo](https://example.com/old) | Unknown | 72 | [Files](jobs/old/) |",
                "<!-- JOBS_TABLE_END -->",
            ]
        ),
        encoding="utf-8",
    )

    with (
        patch("job_hunter.pipeline.stages.processing.ROOT", str(tmp_path)),
        patch("job_hunter.pipeline.stages.processing._today", return_value="2026-05-25"),
    ):
        processing.update_readme([])

    content = readme.read_text(encoding="utf-8")
    assert "**Application stats:** stale" not in content
    assert "**Application stats:** 1 job tracked since 2026-05-05 (3 weeks)." in content


def test_skip_validate_bypasses_validate_call() -> None:
    jobs = [_match(0)["job"]]

    with (
        patch("job_hunter.pipeline.stages.processing.validate") as validate,
        patch("job_hunter.pipeline.stages.processing.score_and_filter_jobs", return_value=[]),
    ):
        processing.process_jobs(
            jobs,
            skip_validate=True,
            skip_score=False,
            max_years=4,
            api_config={},
            scoring_config={"scoring": {}},
        )

    validate.assert_not_called()


def test_skip_score_bypasses_scoring_and_wraps_jobs_as_zero_score_matches() -> None:
    jobs = [_match(0)["job"], _match(1)["job"]]
    processed_matches = []

    def fake_process(match) -> bool:
        processed_matches.append(match)
        return True

    with (
        patch("job_hunter.pipeline.stages.processing.score_and_filter_jobs") as score_and_filter_jobs,
        patch("job_hunter.pipeline.stages.processing._process_match", side_effect=fake_process),
    ):
        processed = processing.process_jobs(
            jobs,
            skip_validate=True,
            skip_score=True,
            max_years=4,
            api_config={},
            scoring_config={"scoring": {}},
        )

    score_and_filter_jobs.assert_not_called()
    assert len(processed) == 2
    assert all(match["score"] == 0 for match in processed_matches)


def test_quality_gate_rejecting_all_jobs_yields_no_processed_matches() -> None:
    jobs = [_match(0)["job"]]

    with (
        patch("job_hunter.pipeline.stages.processing.apply_pre_scoring_quality_gate", return_value=([], jobs)),
        patch("job_hunter.pipeline.stages.processing.score_and_filter_jobs") as score_and_filter_jobs,
    ):
        processed = processing.process_jobs(
            jobs,
            skip_validate=True,
            skip_score=False,
            max_years=4,
            api_config={},
            scoring_config={"scoring": {}},
        )

    assert processed == []
    score_and_filter_jobs.assert_not_called()


def test_one_failing_match_does_not_stop_the_rest_of_the_batch() -> None:
    matches = [_match(idx) for idx in range(3)]
    attempted = []

    def fake_process(match) -> bool:
        attempted.append(match["job"]["title"])
        if match["job"]["title"] == "Product Manager 1":
            raise RuntimeError("boom")
        return True

    with (
        patch("job_hunter.pipeline.stages.processing.score_and_filter_jobs", return_value=matches),
        patch("job_hunter.pipeline.stages.processing._process_match", side_effect=fake_process),
    ):
        processed = processing.process_jobs(
            [m["job"] for m in matches],
            skip_validate=True,
            skip_score=False,
            max_years=4,
            api_config={},
            scoring_config={"scoring": {}},
        )

    # all three were attempted despite the middle one raising
    assert attempted == ["Product Manager 0", "Product Manager 1", "Product Manager 2"]
    # only the two that didn't raise made it into the processed batch
    assert [m["job"]["title"] for m in processed] == ["Product Manager 0", "Product Manager 2"]


def test_hard_screen_rejects_excluded_industry() -> None:
    from job_hunter.pipeline.stages.screening import screen_jobs_by_rules

    jobs = [
        {
            "title": "Product Manager",
            "company": "Workflow SaaS",
            "snippet": "Build software used by banking customers.",
            "region": "berlin",
        }
    ]
    config = {
        "job_titles": ["Product Manager"],
        "exclusions": {"industries": ["banking"]},
        "regions": {"berlin": {"location": "Berlin"}},
    }

    kept, rejected = screen_jobs_by_rules(jobs, config)

    assert kept == []
    assert rejected[0]["_rejection_reason"] == "excluded_industry"


def test_hard_screen_rejects_german_posting_when_hunt_languages_is_english_only() -> None:
    from job_hunter.pipeline.stages.screening import screen_jobs_by_rules

    jobs = [
        {
            "title": "PM",
            "company": "Workflow SaaS",
            "snippet": "Wir suchen einen erfahrenen Produktmanager fuer unser Team in Berlin.",
            "location": "Berlin, Germany",
            "region": "de",
        }
    ]
    config = {
        "job_titles": ["PM"],
        "filters": {"hunt_languages": ["en"]},
        "regions": {"de": {"enabled": True, "country": "DE", "scope": "country"}},
    }

    kept, rejected = screen_jobs_by_rules(jobs, config)

    assert kept == []
    assert rejected[0]["_rejection_reason"] == "language_not_hunted"


def test_hard_screen_keeps_low_confidence_language_and_flags_it_for_review() -> None:
    from job_hunter.pipeline.stages.screening import screen_jobs_by_rules

    jobs = [
        {
            "title": "Manager",
            "company": "Workflow SaaS",
            "snippet": "",
            "location": "Berlin, Germany",
            "region": "de",
        }
    ]
    config = {
        "job_titles": ["Manager"],
        "filters": {"hunt_languages": ["en"]},
        "regions": {"de": {"enabled": True, "country": "DE", "scope": "country"}},
    }

    kept, rejected = screen_jobs_by_rules(jobs, config)

    assert rejected == []
    assert kept[0]["_judgment_signals"]["language_uncertain"] is True


def test_finalize_processed_batch_updates_readme_and_upserts_successful_application(tmp_path) -> None:
    match = {"score": 90, "job": {"title": "PM", "company": "Acme", "url": "https://example.com/pm"}}

    with (
        patch("job_hunter.pipeline.stages.processing.update_readme") as update_readme,
        patch("job_hunter.pipeline.stages.processing.upsert_application_from_job") as upsert,
    ):
        processing.finalize_processed_batch([match], {"https://example.com/old"})

    update_readme.assert_called_once_with([match])
    upsert.assert_called_once()
    assert upsert.call_args.args[0].endswith("_acme_pm")


def test_finalize_processed_batch_is_a_noop_when_nothing_processed() -> None:
    with (
        patch("job_hunter.pipeline.stages.processing.update_readme") as update_readme,
        patch("job_hunter.pipeline.stages.processing.upsert_application_from_job") as upsert,
    ):
        processing.finalize_processed_batch([], set())

    update_readme.assert_not_called()
    upsert.assert_not_called()


def test_finalize_processed_batch_one_bad_upsert_does_not_abort_the_rest() -> None:
    """One match's upsert raising (e.g. a race on score.yml) must not skip the
    remaining matches' upserts or the README update."""
    broken = {"score": 90, "job": {"title": "Broken", "company": "BadCo", "url": "https://example.com/bad"}}
    ok = {"score": 80, "job": {"title": "PM", "company": "Acme", "url": "https://example.com/pm"}}

    def side_effect(slug, **_kwargs):
        if "badco" in slug:
            raise ValueError("refusing to create an application: score.yml is missing")

    with (
        patch("job_hunter.pipeline.stages.processing.update_readme") as update_readme,
        patch("job_hunter.pipeline.stages.processing.upsert_application_from_job", side_effect=side_effect) as upsert,
    ):
        processing.finalize_processed_batch([broken, ok], set())

    assert upsert.call_count == 2
    update_readme.assert_called_once_with([broken, ok])


def test_excluded_title_jobs_never_reach_llm_scoring() -> None:
    """Objective screening runs before the quality gate and before scoring, so
    an excluded-title job must never appear in score_and_filter_jobs input."""
    good = {**_match(0)["job"], "location": "Berlin, Germany"}
    excluded = {**_match(1)["job"], "title": "Staff Product Manager", "location": "Berlin, Germany"}
    scored_inputs: list[list[dict]] = []

    def fake_score(jobs, config):
        scored_inputs.append(jobs)
        return [{"score": 90, "matched_keywords": [], "gaps": [], "job": job} for job in jobs]

    with (
        patch("job_hunter.pipeline.stages.processing.score_and_filter_jobs", side_effect=fake_score),
        patch("job_hunter.pipeline.stages.processing._process_match", return_value=True),
    ):
        processing.process_jobs(
            [good, excluded],
            skip_validate=True,
            skip_score=False,
            max_years=4,
            api_config={},
            scoring_config={
                "scoring": {},
                "exclusions": {"title_terms": ["staff"]},
                "regions": {"de": {"enabled": True, "country": "DE", "scope": "country"}},
            },
        )

    assert len(scored_inputs) == 1
    scored_titles = [job["title"] for job in scored_inputs[0]]
    assert "Staff Product Manager" not in scored_titles
    assert good["title"] in scored_titles


def test_hard_screen_stamps_detected_language_on_kept_jobs() -> None:
    from job_hunter.pipeline.stages.screening import screen_jobs_by_rules

    jobs = [
        {
            "title": "Produktmanager",
            "company": "Workflow SaaS",
            "snippet": "Wir suchen einen erfahrenen Produktmanager fuer unser Team in Berlin. "
            "Du verantwortest die Produktstrategie und arbeitest eng mit Entwicklung zusammen.",
            "location": "Berlin, Germany",
            "region": "de",
        }
    ]
    config = {
        "job_titles": ["Produktmanager"],
        "filters": {"hunt_languages": ["en", "de"]},
        "regions": {"de": {"enabled": True, "country": "DE", "scope": "country"}},
    }

    kept, rejected = screen_jobs_by_rules(jobs, config)

    assert rejected == []
    assert kept[0]["language"] == "de"


def test_insert_jobs_persists_detected_language(tmp_path) -> None:
    import sqlite3

    from job_hunter.tracking.repository import insert_jobs

    insert_jobs(tmp_path, [{"url": "https://x.example/j1", "title": "PM", "company": "X", "language": "de"}])

    db = tmp_path / "outputs" / "state" / "jobs.db"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT language, output_language FROM jobs WHERE url = ?", ("https://x.example/j1",)
        ).fetchone()
    assert row == ("de", "")
