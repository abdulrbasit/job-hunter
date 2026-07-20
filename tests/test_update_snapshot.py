"""Tests for job_hunter/update/snapshot.py — snapshot/rollback of system-owned files."""

from __future__ import annotations

from pathlib import Path

from job_hunter.update.snapshot import rollback_last, snapshot_system_files


def _make_workspace(root: Path) -> None:
    (root / "config" / "schemas").mkdir(parents=True)
    (root / "config" / "schemas" / "job_hunter.schema.json").write_text('{"v": 1}', encoding="utf-8")
    (root / "README.md").write_text("original readme", encoding="utf-8")
    (root / ".claude" / "skills" / "job-hunter").mkdir(parents=True)
    (root / ".claude" / "skills" / "job-hunter" / "SKILL.md").write_text("skill v1", encoding="utf-8")
    # user-owned — must never be snapshotted or rolled back
    (root / "config" / "job_hunter.yml").write_text("mode: agent\n", encoding="utf-8")


def test_snapshot_then_rollback_restores_overwritten_system_files(tmp_path: Path) -> None:
    _make_workspace(tmp_path)

    count = snapshot_system_files(tmp_path)
    assert count == 3  # README.md, schema.json, SKILL.md

    # Simulate an update overwriting system files.
    (tmp_path / "README.md").write_text("new readme", encoding="utf-8")
    (tmp_path / ".claude" / "skills" / "job-hunter" / "SKILL.md").write_text("skill v2", encoding="utf-8")

    restored = rollback_last(tmp_path)
    assert restored == 3
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "original readme"
    assert (tmp_path / ".claude" / "skills" / "job-hunter" / "SKILL.md").read_text(encoding="utf-8") == "skill v1"


def test_snapshot_never_captures_user_owned_files(tmp_path: Path) -> None:
    _make_workspace(tmp_path)
    snapshot_system_files(tmp_path)

    snapshot_root = tmp_path / "outputs" / "state" / "update_snapshot"
    assert not (snapshot_root / "config" / "job_hunter.yml").exists()


def test_rollback_with_no_prior_snapshot_returns_zero(tmp_path: Path) -> None:
    _make_workspace(tmp_path)
    assert rollback_last(tmp_path) == 0


def test_snapshot_replaces_prior_snapshot_rather_than_accumulating(tmp_path: Path) -> None:
    _make_workspace(tmp_path)
    snapshot_system_files(tmp_path)
    (tmp_path / "README.md").unlink()  # next snapshot should reflect current (fewer) files
    count = snapshot_system_files(tmp_path)
    assert count == 2
