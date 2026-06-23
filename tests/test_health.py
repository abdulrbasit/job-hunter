from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.ux.health import onboarding_status


def _write_minimal_repo(root: Path) -> None:
    (root / "config").mkdir()
    (root / "profile").mkdir()
    (root / "outputs").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump(
            {
                "mode": "agent",
                "profile": {
                    "resume_tex": "profile/resume_double_column.tex",
                    "story_bank": "profile/story_bank.md",
                },
                "job_titles": [],
                "regions": {},
                "exclusions": {},
                "sources": {},
                "scoring": {"min_fit_score": 70},
                "linkedin": {"enabled": False},
                "llm": {"default_provider": "anthropic"},
                "secrets": {},
            }
        ),
        encoding="utf-8",
    )
    (root / "profile" / "story_bank.md").write_text(
        "# Story Bank\n\n# Final - refined STAR stories\n<!-- none -->\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows" / "find-jobs.yml").write_text(
        "name: Find Jobs\non:\n  workflow_dispatch:\n",
        encoding="utf-8",
    )


def test_onboarding_status_reports_missing_items(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    for key in (
        "BRAVE_API_KEY",
        "TAVILY_API_KEY",
        "EXA_API_KEY",
        "SEARXNG_BASE_URL",
        "ADZUNA_APP_ID",
        "ADZUNA_API_KEY",
        "REED_API_KEY",
        "RAPIDAPI_KEY",
        "JOOBLE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    payload = onboarding_status(tmp_path)

    assert payload["onboardingNeeded"] is True
    assert "config/job_hunter.yml:regions" in payload["missing"]
    assert "profile/resume_double_column.tex" in payload["missing"]
    assert "profile/story_bank.md:final_stories" in payload["missing"]
    assert "api_keys" in payload["missing"]


def test_onboarding_status_passes_when_required_user_files_are_ready(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    monkeypatch.setenv("BRAVE_API_KEY", "test")
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump(
            {
                "mode": "agent",
                "profile": {
                    "resume_tex": "profile/resume_double_column.tex",
                    "story_bank": "profile/story_bank.md",
                },
                "job_titles": ["Product Manager"],
                "regions": {"berlin": {"enabled": True, "location": "Berlin", "country": "DE"}},
                "exclusions": {},
                "sources": {},
                "scoring": {"min_fit_score": 70},
                "linkedin": {"enabled": False},
                "llm": {"default_provider": "anthropic"},
                "secrets": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "profile" / "resume_double_column.tex").write_text("resume", encoding="utf-8")
    (tmp_path / "profile" / "story_bank.md").write_text(
        "# Story Bank\n\n# Final - refined STAR stories\n\n## PM-01\nStory.\n",
        encoding="utf-8",
    )

    payload = onboarding_status(tmp_path)

    assert payload["onboardingNeeded"] is False
    assert payload["missing"] == []
