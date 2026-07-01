"""Tests for pipeline/stages/metrics.py — metrics persistence must never crash the pipeline run."""

from unittest.mock import patch

from job_hunter.pipeline.context import PipelineCommandOptions, PipelineRunContext
from job_hunter.pipeline.stages import metrics


def _ctx() -> PipelineRunContext:
    return PipelineRunContext(
        options=PipelineCommandOptions(mode="hunt", region="primary"),
        api_cfg={},
        scoring_cfg={},
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
