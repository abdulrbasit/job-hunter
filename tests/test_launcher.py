"""Tests for job_hunter/launcher.py — recent-workspace resolution and create/open."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from job_hunter import launcher


@pytest.fixture(autouse=True)
def _isolated_platform_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect platform_config_dir() into tmp_path so tests never touch the real %APPDATA%/~/.config."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))


def _make_valid_workspace(path: Path) -> None:
    (path / "config").mkdir(parents=True)
    (path / "config" / "job_hunter.yml").write_text("mode: agent\n", encoding="utf-8")


def test_get_recent_workspace_returns_none_when_unset() -> None:
    assert launcher.get_recent_workspace() is None


def test_set_then_get_recent_workspace_round_trips(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _make_valid_workspace(workspace)

    launcher.set_recent_workspace(workspace)

    assert launcher.get_recent_workspace() == workspace.resolve()


def test_get_recent_workspace_returns_none_when_directory_gone(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _make_valid_workspace(workspace)
    launcher.set_recent_workspace(workspace)
    shutil.rmtree(workspace)

    assert launcher.get_recent_workspace() is None


def test_get_recent_workspace_returns_none_when_no_longer_a_valid_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _make_valid_workspace(workspace)
    launcher.set_recent_workspace(workspace)
    (workspace / "config" / "job_hunter.yml").unlink()

    assert launcher.get_recent_workspace() is None


def test_resolve_launch_root_matches_recent_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _make_valid_workspace(workspace)
    launcher.set_recent_workspace(workspace)

    assert launcher.resolve_launch_root() == workspace.resolve()


def test_resolve_launch_root_is_none_with_no_recent_workspace() -> None:
    assert launcher.resolve_launch_root() is None


def test_is_valid_workspace_true_for_manifest_only(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / ".job-hunter").mkdir(parents=True)
    (workspace / ".job-hunter" / "manifest.json").write_text("{}", encoding="utf-8")

    assert launcher.is_valid_workspace(workspace) is True


def test_is_valid_workspace_false_for_empty_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    assert launcher.is_valid_workspace(workspace) is False


def test_open_workspace_rejects_non_workspace_directory(tmp_path: Path) -> None:
    not_a_workspace = tmp_path / "not-a-workspace"
    not_a_workspace.mkdir()

    with pytest.raises(FileNotFoundError):
        launcher.open_workspace(not_a_workspace)


def test_open_workspace_sets_recent_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _make_valid_workspace(workspace)

    result = launcher.open_workspace(workspace)

    assert result == workspace.resolve()
    assert launcher.get_recent_workspace() == workspace.resolve()


def test_create_workspace_rejects_non_empty_target_without_force(tmp_path: Path) -> None:
    from job_hunter.workspace.operations import WorkspaceNotEmptyError

    target = tmp_path / "ws"
    target.mkdir()
    (target / "existing.txt").write_text("x", encoding="utf-8")

    with pytest.raises(WorkspaceNotEmptyError):
        launcher.create_workspace(target)


def test_create_workspace_sets_recent_workspace(tmp_path: Path) -> None:
    target = tmp_path / "ws"

    result = launcher.create_workspace(target)

    assert launcher.get_recent_workspace() == result.workspace.resolve()


def test_bootstrap_launch_state_reports_no_recent_workspace() -> None:
    assert launcher.bootstrap_launch_state() == {"recent_workspace": None}


def test_bootstrap_launch_state_reports_recent_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _make_valid_workspace(workspace)
    launcher.set_recent_workspace(workspace)

    assert launcher.bootstrap_launch_state() == {"recent_workspace": str(workspace.resolve())}
