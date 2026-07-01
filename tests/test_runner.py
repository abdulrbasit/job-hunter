"""Tests for pipeline/runner.py — typed mode dispatch."""

from unittest.mock import MagicMock, patch

import pytest

from job_hunter.pipeline import runner
from job_hunter.pipeline.context import PipelineCommandOptions


def test_hunt_no_new_jobs_is_successful_empty_run() -> None:
    options = PipelineCommandOptions(mode="hunt", region="magdeburg")

    with (
        patch("job_hunter.pipeline.runner.get_api_config", return_value={}),
        patch("job_hunter.pipeline.runner.get_config", return_value={"scoring": {}}),
        patch("job_hunter.pipeline.modes.hunt.run_hunt", return_value=([], set(), set())),
    ):
        result = runner.run(options)

    assert result.exit_code == 0


def test_hunt_scrape_only_emits_github_action_output_lines(tmp_path, capsys) -> None:
    options = PipelineCommandOptions(mode="hunt", region="primary", scrape_only=True)
    snapshot = tmp_path / "hunt_scrape_2026-06-11_primary.json"

    with (
        patch("job_hunter.pipeline.runner.get_api_config", return_value={}),
        patch("job_hunter.pipeline.runner.get_config", return_value={"scoring": {}}),
        patch(
            "job_hunter.pipeline.modes.hunt.run_hunt_scrape_only",
            return_value=(snapshot, 2, MagicMock()),
        ),
    ):
        result = runner.run(options)

    assert result.exit_code == 0
    output = capsys.readouterr().out
    assert f"snapshot_path={snapshot.as_posix()}" in output
    assert "candidate_count=2" in output
    assert "has_candidates=true" in output


def test_hunt_from_snapshot_preserves_tracker_context() -> None:
    options = PipelineCommandOptions(mode="hunt", from_snapshot="snapshot.json", skip_validate=True, skip_score=True)
    job = {
        "title": "Product Manager",
        "company": "Acme",
        "url": "https://example.com/new",
        "snippet": "Role.",
    }
    processed = [{"job": job, "score": 0}]
    existing_urls = {"https://example.com/old"}

    with (
        patch("job_hunter.pipeline.runner.get_api_config", return_value={}),
        patch("job_hunter.pipeline.runner.get_config", return_value={"scoring": {}}),
        patch(
            "job_hunter.pipeline.modes.hunt.load_hunt_snapshot",
            return_value=([job], existing_urls, set()),
        ),
        patch("job_hunter.pipeline.runner.process_jobs", return_value=processed),
        patch("job_hunter.pipeline.stages.processing.update_readme"),
        patch("job_hunter.pipeline.stages.processing.mark_processed") as mark_processed,
    ):
        result = runner.run(options)

    assert result.exit_code == 0
    mark_processed.assert_called_once_with([job], existing_urls)


def test_tailor_links_mode_routes_through_run_tailor() -> None:
    options = PipelineCommandOptions(
        mode="tailor-links", links="https://example.com/job", skip_validate=True, skip_score=True
    )
    job = {"title": "Product Manager", "company": "Acme", "url": options.links, "snippet": "Role."}

    with (
        patch("job_hunter.pipeline.runner.get_api_config", return_value={}),
        patch("job_hunter.pipeline.runner.get_config", return_value={"scoring": {}}),
        patch(
            "job_hunter.pipeline.modes.tailor_links.run_tailor",
            return_value=([job], set(), set()),
        ) as run_tailor,
        patch("job_hunter.pipeline.stages.processing.process_jobs", return_value=[]),
    ):
        result = runner.run(options)

    assert result.exit_code == 0
    run_tailor.assert_called_once()


def test_tailor_links_mode_without_links_or_env_var_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAILOR_LINKS", raising=False)
    options = PipelineCommandOptions(mode="tailor-links", skip_validate=True, skip_score=True)

    with (
        patch("job_hunter.pipeline.runner.get_api_config", return_value={}),
        patch("job_hunter.pipeline.runner.get_config", return_value={"scoring": {}}),
    ):
        result = runner.run(options)

    assert result.exit_code == 1


def test_tailor_raw_mode_routes_through_run_tailor() -> None:
    options = PipelineCommandOptions(
        mode="tailor-raw",
        jd="Full job description text.",
        title="Product Manager",
        company="Acme",
        skip_validate=True,
        skip_score=True,
    )
    job = {"title": "Product Manager", "company": "Acme", "url": "raw://acme", "snippet": "Role."}

    with (
        patch("job_hunter.pipeline.runner.get_api_config", return_value={}),
        patch("job_hunter.pipeline.runner.get_config", return_value={"scoring": {}}),
        patch(
            "job_hunter.pipeline.modes.tailor_raw.run_tailor",
            return_value=([job], set(), set()),
        ) as run_tailor,
        patch("job_hunter.pipeline.stages.processing.process_jobs", return_value=[]),
    ):
        result = runner.run(options)

    assert result.exit_code == 0
    run_tailor.assert_called_once()


def test_tailor_raw_mode_without_jd_fails() -> None:
    options = PipelineCommandOptions(mode="tailor-raw", skip_validate=True, skip_score=True)

    with (
        patch("job_hunter.pipeline.runner.get_api_config", return_value={}),
        patch("job_hunter.pipeline.runner.get_config", return_value={"scoring": {}}),
    ):
        result = runner.run(options)

    assert result.exit_code == 1
