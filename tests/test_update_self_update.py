"""Tests for job_hunter/update/self_update.py — the detached upgrade-and-relaunch helper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from job_hunter.update import self_update
from job_hunter.update.upgrader import Upgrader


@pytest.fixture(autouse=True)
def _isolated_platform_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))


@pytest.fixture(autouse=True)
def _no_real_sleep() -> None:
    with patch("time.sleep"):
        yield


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_run_self_update_success_writes_result_and_relaunches(tmp_path: Path) -> None:
    upgrader = Upgrader("uv", ["uv", "tool", "upgrade", "job-hunter-kit"])
    with (
        patch("subprocess.run", return_value=_proc(0)) as mock_run,
        patch("subprocess.Popen") as mock_popen,
        patch("job_hunter.update.versions.installed_version", return_value="0.26"),
    ):
        result = self_update.run_self_update(tmp_path, upgrader, from_version="0.25")

    assert result == {"ok": True, "stage": "done", "from": "0.25", "to": "0.26"}
    assert mock_run.call_count == 2  # upgrade command, then `job-hunter update --yes`
    mock_popen.assert_called_once()
    assert mock_popen.call_args.args[0][:2] == ["job-hunter", "dash"]

    stored = self_update.read_last_result()
    assert stored == result


def test_run_self_update_retries_upgrade_on_transient_failure_then_succeeds(tmp_path: Path) -> None:
    upgrader = Upgrader("pip", ["pip", "install", "--upgrade", "job-hunter-kit"])
    attempts = [_proc(1, stderr="locked"), _proc(1, stderr="locked"), _proc(0), _proc(0)]
    with (
        patch("subprocess.run", side_effect=attempts) as mock_run,
        patch("subprocess.Popen"),
        patch("job_hunter.update.versions.installed_version", return_value="0.26"),
    ):
        result = self_update.run_self_update(tmp_path, upgrader, from_version="0.25")

    assert result["ok"] is True
    assert mock_run.call_count == 4  # 2 failed upgrade attempts + 1 successful + workspace update


def test_run_self_update_gives_up_after_max_retries_and_reports_fallback(tmp_path: Path) -> None:
    upgrader = Upgrader("pip", ["pip", "install", "--upgrade", "job-hunter-kit"])
    with (
        patch("subprocess.run", return_value=_proc(1, stderr="permission denied")),
        patch("subprocess.Popen") as mock_popen,
    ):
        result = self_update.run_self_update(tmp_path, upgrader, from_version="0.25")

    assert result["ok"] is False
    assert result["stage"] == "upgrade"
    assert result["fallback_command"] == "pip install --upgrade job-hunter-kit"
    mock_popen.assert_not_called()  # never relaunches on a failed upgrade
    assert self_update.read_last_result() == result


def test_run_self_update_reports_workspace_update_failure_separately(tmp_path: Path) -> None:
    upgrader = Upgrader("uv", ["uv", "tool", "upgrade", "job-hunter-kit"])
    with (
        patch("subprocess.run", side_effect=[_proc(0), _proc(1, stderr="schema invalid")]),
        patch("subprocess.Popen") as mock_popen,
    ):
        result = self_update.run_self_update(tmp_path, upgrader, from_version="0.25")

    assert result["ok"] is False
    assert result["stage"] == "workspace_update"
    assert result["fallback_command"] == "job-hunter update --yes"
    mock_popen.assert_not_called()


def test_read_last_result_is_none_when_absent(tmp_path: Path) -> None:
    assert self_update.read_last_result() is None


def test_clear_last_result_is_idempotent(tmp_path: Path) -> None:
    self_update.clear_last_result()
    self_update.clear_last_result()
