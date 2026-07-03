from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from job_hunter.workspace.safety import (
    changed_paths_from_status,
    classify_path,
    dirty_system_paths,
    unsafe_update_paths,
    update_safety_report,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    return tmp_path


def test_classifies_user_and_system_paths() -> None:
    assert classify_path("config/job_hunter.yml") == "user"
    assert classify_path("profile/story_bank.md") == "user"
    assert classify_path("outputs/applications.yml") == "user"
    assert classify_path("config/schemas/job_hunter.schema.json") == "system"
    assert classify_path("job_hunter/health.py") == "system"
    assert classify_path(".claude/skills/setup/SKILL.md") == "system"
    assert classify_path("job_hunter/") == "system"
    assert classify_path("unknown.txt") == "unknown"


def test_unsafe_update_paths_rejects_user_and_unknown_paths() -> None:
    unsafe = unsafe_update_paths(
        [
            "job_hunter/health.py",
            "config/job_hunter.yml",
            "notes.txt",
        ]
    )

    assert unsafe == ["config/job_hunter.yml", "notes.txt"]


def test_unsafe_update_paths_always_rejects_user_config() -> None:
    unsafe = unsafe_update_paths(
        [
            "config/job_hunter.yml",
            "profile/story_bank.md",
        ]
    )

    assert unsafe == ["config/job_hunter.yml", "profile/story_bank.md"]


def test_changed_paths_from_status_handles_renames() -> None:
    status = " M job_hunter/health.py\nR  old.txt -> config/job_hunter.yml\n"

    assert changed_paths_from_status(status) == [
        "job_hunter/health.py",
        "config/job_hunter.yml",
    ]


def test_update_safety_report_with_explicit_paths(tmp_path: Path) -> None:
    report = update_safety_report(
        tmp_path,
        paths=["job_hunter/health.py", "outputs/applications.yml"],
    )

    assert report["ok"] is False
    assert report["unsafe"] == ["outputs/applications.yml"]


def test_update_safety_report_rejects_user_config(tmp_path: Path) -> None:
    report = update_safety_report(
        tmp_path,
        paths=["job_hunter/health.py", "config/job_hunter.yml"],
    )

    assert report["ok"] is False
    assert report["unsafe"] == ["config/job_hunter.yml"]


def test_dirty_system_paths_flags_modified_skill_but_not_user_config(tmp_path: Path) -> None:
    """`job-hunter update` is about to overwrite system-layer files (skills, workflows) —
    a dirty system file means the user's local edit to it is about to be discarded. A
    dirty user-layer file (config/profile/outputs) is normal and must not be flagged."""
    root = _git_repo(tmp_path)
    skill = root / ".claude" / "skills" / "job-hunter" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("original\n", encoding="utf-8")
    config = root / "config" / "job_hunter.yml"
    config.parent.mkdir(parents=True)
    config.write_text("mode: agent\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "add files")

    skill.write_text("locally edited\n", encoding="utf-8")
    config.write_text("mode: llm-api\n", encoding="utf-8")

    dirty = dirty_system_paths(root)

    assert ".claude/skills/job-hunter/SKILL.md" in dirty
    assert "config/job_hunter.yml" not in dirty


def test_dirty_system_paths_raises_when_not_a_git_repo(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        dirty_system_paths(tmp_path)
