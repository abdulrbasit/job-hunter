from __future__ import annotations

from pathlib import Path

from job_hunter.data_contract import (
    changed_paths_from_status,
    classify_path,
    unsafe_update_paths,
)
from job_hunter.update_safety import update_safety_report


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
