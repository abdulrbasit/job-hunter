"""Tests for cli/dispatch.py — CLI-flag to pipeline-input wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from job_hunter.cli.dispatch import dispatch_hunt
from job_hunter.models import HuntOutput, ScrapeStats


def _stub_output() -> HuntOutput:
    return HuntOutput(stats=ScrapeStats(), mode="agent")


def test_dispatch_hunt_passes_depth_into_hunt_input() -> None:
    with (
        patch("job_hunter.config.get_mode", return_value="agent"),
        patch("job_hunter.pipeline.hunt.run", return_value=_stub_output()) as mock_run,
    ):
        dispatch_hunt(depth="deep")

    passed_input = mock_run.call_args[0][0]
    assert passed_input.depth == "deep"


def test_dispatch_hunt_passes_force_into_hunt_input() -> None:
    with (
        patch("job_hunter.config.get_mode", return_value="agent"),
        patch("job_hunter.pipeline.hunt.run", return_value=_stub_output()) as mock_run,
    ):
        dispatch_hunt(force=True)

    passed_input = mock_run.call_args[0][0]
    assert passed_input.force is True


def test_dispatch_hunt_defaults_depth_to_standard() -> None:
    with (
        patch("job_hunter.config.get_mode", return_value="agent"),
        patch("job_hunter.pipeline.hunt.run", return_value=_stub_output()) as mock_run,
    ):
        dispatch_hunt()

    passed_input = mock_run.call_args[0][0]
    assert passed_input.depth == "standard"


def test_dispatch_hunt_from_db_candidates_in_agent_mode_fails_cleanly(capsys) -> None:
    """A pydantic ValidationError must never reach the user as a raw traceback —
    dispatch_hunt should print one clean line and exit, not construct HuntInput unguarded."""
    with (
        patch("job_hunter.config.get_mode", return_value="agent"),
        patch("job_hunter.pipeline.hunt.run") as mock_run,
        pytest.raises(typer.Exit) as exc_info,
    ):
        dispatch_hunt(from_db_candidates=True)

    mock_run.assert_not_called()
    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "/job-hunter batch" in captured.err
    assert "ValidationError" not in captured.err
    assert "Traceback" not in captured.err
