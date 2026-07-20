"""Tests for job_hunter/shortcut.py — first-run desktop shortcut, opt-out."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from job_hunter import shortcut


@pytest.fixture(autouse=True)
def _isolated_platform_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))


def _proc(returncode: int) -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    return result


def test_record_opt_out_then_ensure_shortcut_is_a_no_op() -> None:
    shortcut.record_opt_out()

    with patch("shutil.which", return_value="/usr/bin/job-hunter") as mock_which:
        shortcut.ensure_desktop_shortcut()

    mock_which.assert_not_called()  # short-circuited before touching the OS at all


def test_ensure_desktop_shortcut_creates_linux_desktop_entry(tmp_path: Path) -> None:
    with (
        patch.object(sys, "platform", "linux"),
        patch("shutil.which", return_value="/usr/bin/job-hunter"),
        patch.object(Path, "home", return_value=tmp_path),
    ):
        shortcut.ensure_desktop_shortcut()

    entry = tmp_path / ".local" / "share" / "applications" / "job-hunter.desktop"
    assert entry.exists()
    assert "Exec=/usr/bin/job-hunter dash" in entry.read_text(encoding="utf-8")


def test_ensure_desktop_shortcut_is_idempotent_on_linux(tmp_path: Path) -> None:
    with (
        patch.object(sys, "platform", "linux"),
        patch("shutil.which", return_value="/usr/bin/job-hunter") as mock_which,
        patch.object(Path, "home", return_value=tmp_path),
    ):
        shortcut.ensure_desktop_shortcut()
        shortcut.ensure_desktop_shortcut()

    assert mock_which.call_count == 1  # second call short-circuits on shortcut_created


def test_ensure_desktop_shortcut_creates_windows_lnk_via_powershell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start_menu = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    start_menu.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    with (
        patch.object(sys, "platform", "win32"),
        patch("shutil.which", return_value="C:\\job-hunter.exe"),
        patch("subprocess.run", return_value=_proc(0)) as mock_run,
    ):
        shortcut.ensure_desktop_shortcut()

    mock_run.assert_called_once()
    assert mock_run.call_args.args[0][0] == "powershell"


def test_ensure_desktop_shortcut_records_nothing_when_creation_fails() -> None:
    # APPDATA (from the autouse fixture) has no Start Menu\Programs dir under it, so
    # _create_windows_shortcut returns False without ever calling subprocess.
    with (
        patch.object(sys, "platform", "win32"),
        patch("shutil.which", return_value="C:\\job-hunter.exe"),
        patch("subprocess.run") as mock_run,
    ):
        shortcut.ensure_desktop_shortcut()

    mock_run.assert_not_called()
    assert shortcut._read_state().get("shortcut_created") is not True


def test_ensure_desktop_shortcut_is_noop_on_macos() -> None:
    with patch.object(sys, "platform", "darwin"), patch("shutil.which") as mock_which:
        shortcut.ensure_desktop_shortcut()

    mock_which.assert_not_called()


def test_ensure_desktop_shortcut_swallows_oserror(tmp_path: Path) -> None:
    with (
        patch.object(sys, "platform", "linux"),
        patch("shutil.which", side_effect=OSError("boom")),
    ):
        shortcut.ensure_desktop_shortcut()  # must not raise
