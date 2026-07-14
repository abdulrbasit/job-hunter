"""Tests for job_hunter/ux/web/readiness.py — Get Started blocking/non-blocking checks."""

from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.ux.web.readiness import get_readiness

_READY_CONFIG = {
    "mode": "agent",
    "job_titles": ["Product Manager"],
    "career_stage": "experienced",
    "regions": {"primary": {"enabled": True, "country": "DE", "location": "Berlin"}},
    "profile": {
        "resume_tex": "profile/resume_double_column.tex",
        "story_bank": "profile/story_bank.md",
        "career_context": "profile/career_context.md",
    },
}


def _write_workspace(
    root: Path, config: dict, *, resume_filled: bool = True, career_context_filled: bool = True
) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "job_hunter.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (root / "profile").mkdir(parents=True, exist_ok=True)
    resume_text = "not a template placeholder" if resume_filled else r"\name{Name}"
    (root / "profile" / "resume_double_column.tex").write_text(resume_text, encoding="utf-8")
    if career_context_filled:
        context = (
            "- Current role: Senior Product Manager at Example Corp\n"
            "- Experience summary: 5 years in B2B SaaS product management\n"
            "- Strongest proof points: Led product from 0 to 10k users\n"
        )
    else:
        context = ""
    (root / "profile" / "career_context.md").write_text(context, encoding="utf-8")


def test_empty_workspace_is_not_ready(tmp_path: Path) -> None:
    readiness = get_readiness(tmp_path)

    assert readiness["ready"] is False
    assert readiness["blocking"]["job_titles"] is False


def test_fully_filled_workspace_is_ready(tmp_path: Path) -> None:
    _write_workspace(tmp_path, _READY_CONFIG)

    readiness = get_readiness(tmp_path)

    assert readiness["blocking"] == {
        "job_titles": True,
        "career_stage": True,
        "region": True,
        "career_context": True,
        "base_resume": True,
        "api_key": True,
    }
    assert readiness["ready"] is True


def test_missing_career_stage_key_is_still_valid_via_custom_default(tmp_path: Path) -> None:
    config = dict(_READY_CONFIG)
    config.pop("career_stage")
    _write_workspace(tmp_path, config)

    readiness = get_readiness(tmp_path)

    assert readiness["blocking"]["career_stage"] is True


def test_unfilled_career_context_blocks_readiness(tmp_path: Path) -> None:
    _write_workspace(tmp_path, _READY_CONFIG, career_context_filled=False)

    readiness = get_readiness(tmp_path)

    assert readiness["blocking"]["career_context"] is False
    assert readiness["ready"] is False


def test_unfilled_resume_blocks_readiness(tmp_path: Path) -> None:
    _write_workspace(tmp_path, _READY_CONFIG, resume_filled=False)

    readiness = get_readiness(tmp_path)

    assert readiness["blocking"]["base_resume"] is False
    assert readiness["ready"] is False


def test_missing_final_story_is_non_blocking_not_blocking(tmp_path: Path) -> None:
    """Spec rule: stories improve quality but never block younger users from starting."""
    _write_workspace(tmp_path, _READY_CONFIG)

    readiness = get_readiness(tmp_path)

    assert readiness["ready"] is True
    assert "no_final_story" in readiness["non_blocking"]


def test_missing_github_schedule_is_non_blocking(tmp_path: Path) -> None:
    _write_workspace(tmp_path, _READY_CONFIG)

    readiness = get_readiness(tmp_path)

    assert "no_github_schedule" in readiness["non_blocking"]
