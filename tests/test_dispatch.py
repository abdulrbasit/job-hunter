"""Tests for cli/dispatch.py — CLI-flag to pipeline-input wiring."""

from __future__ import annotations

from unittest.mock import patch

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
