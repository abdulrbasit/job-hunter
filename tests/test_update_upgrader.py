"""Tests for job_hunter/update/upgrader.py — detect which tool manages the install."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from job_hunter.update.upgrader import Upgrader, detect_upgrader


def _proc(returncode: int, stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    return result


def test_detect_upgrader_returns_none_for_frozen_build() -> None:
    with patch.object(sys, "frozen", True, create=True):
        assert detect_upgrader() is None


def test_detect_upgrader_prefers_uv_when_uv_manages_the_package() -> None:
    with (
        patch("shutil.which", side_effect=lambda tool: f"/usr/bin/{tool}" if tool == "uv" else None),
        patch("subprocess.run", return_value=_proc(0, "job-hunter-kit 0.25\n")),
    ):
        result = detect_upgrader()
    assert result == Upgrader("uv", ["uv", "tool", "upgrade", "job-hunter-kit"])


def test_detect_upgrader_falls_back_to_pipx_when_uv_does_not_manage_it() -> None:
    def which(tool: str) -> str | None:
        return f"/usr/bin/{tool}" if tool in ("uv", "pipx") else None

    def run(cmd: list[str], **_kwargs: object) -> MagicMock:
        if cmd[0] == "uv":
            return _proc(0, "some-other-package 1.0\n")
        return _proc(0, "job-hunter-kit 0.25, ...\n")

    with patch("shutil.which", side_effect=which), patch("subprocess.run", side_effect=run):
        result = detect_upgrader()
    assert result == Upgrader("pipx", ["pipx", "upgrade", "job-hunter-kit"])


def test_detect_upgrader_falls_back_to_pip_when_neither_uv_nor_pipx_manage_it() -> None:
    with patch("shutil.which", return_value=None):
        result = detect_upgrader()
    assert result == Upgrader("pip", [sys.executable, "-m", "pip", "install", "--upgrade", "job-hunter-kit"])


def test_detect_upgrader_falls_back_to_pip_when_uv_missing_entirely() -> None:
    with patch("shutil.which", return_value=None), patch("subprocess.run") as mock_run:
        result = detect_upgrader()
    mock_run.assert_not_called()
    assert result.tool == "pip"
