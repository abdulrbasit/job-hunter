"""Tests for pipeline/stages/metrics.py — metrics persistence must never crash the pipeline run."""

from unittest.mock import patch

from job_hunter.pipeline.context import PipelineCommandOptions, PipelineRunContext
from job_hunter.pipeline.stages import metrics


def _ctx() -> PipelineRunContext:
    return PipelineRunContext(
        options=PipelineCommandOptions(mode="hunt", region="primary"),
        api_config={},
        scoring_config={},
        max_years=4,
        url_liveness=None,
        start_ts="2026-07-01T00:00:00+00:00",
        start_mono=0.0,
    )


def test_persist_metrics_swallows_write_failure() -> None:
    with patch("job_hunter.metrics.store.record_run", side_effect=RuntimeError("disk full")):
        metrics.persist_metrics(_ctx(), jobs_found=3, jobs_tailored=1, elapsed=1.2)  # must not raise


def test_persist_metrics_calls_record_run_with_run_context() -> None:
    with (
        patch("job_hunter.metrics.store.record_run") as record_run,
        patch("job_hunter.config.loader.get_mode", return_value="llm-api"),
    ):
        metrics.persist_metrics(_ctx(), jobs_found=5, jobs_tailored=2, elapsed=3.5)

    record_run.assert_called_once()
    kwargs = record_run.call_args.kwargs
    assert kwargs["mode"] == "hunt"
    assert kwargs["region"] == "primary"
    assert kwargs["jobs_found"] == 5
    assert kwargs["jobs_tailored"] == 2
    assert kwargs["duration_s"] == 3.5


def test_persist_metrics_normalizes_llm_api_role_tokens(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("job_hunter.config.loader.ROOT", tmp_path)
    with (
        patch("job_hunter.config.loader.get_mode", return_value="llm-api"),
        patch(
            "job_hunter.llm.token_usage.get_token_totals",
            return_value={"scoring": {"in": 100, "out": 20, "cached": 40}},
        ),
    ):
        metrics.persist_metrics(_ctx(), jobs_found=5, jobs_tailored=2, elapsed=3.5)

    import sqlite3

    from job_hunter.metrics.telemetry import get_telemetry_summary

    db = tmp_path / "outputs" / "state" / "metrics.db"
    summary = get_telemetry_summary(db)
    assert summary["totals"]["input_tokens"] == 100

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT e.output_tokens FROM telemetry_events e "
        "JOIN telemetry_phases p ON p.id = e.phase_id WHERE e.backend='llm-api' AND p.phase='scoring'"
    ).fetchone()
    assert row["output_tokens"] == 20
