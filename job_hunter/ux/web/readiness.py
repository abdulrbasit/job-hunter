"""Get Started readiness: blocking vs non-blocking checks for the Phase 3 onboarding flow.

Reuses job_hunter.ux.health's lower-level checks (resume/career-context-filled,
region, API key) rather than duplicating them; adds the checks health.py doesn't
have yet (job_titles, experience_levels). Deliberately separate from health.onboarding_status,
which drives the pre-existing doctor/dashboard checklist and classifies story_bank as
blocking — this flow follows the spec's "stories improve quality but never block" rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from job_hunter.core.utils import read_yaml
from job_hunter.filters import filter_values
from job_hunter.ux.health import (
    _api_key_configured,
    _career_context_filled,
    _configured_profile_rel,
    _has_enabled_region,
    _has_final_story,
    _resume_filled,
    _workflow_schedule_configured,
)


def get_readiness(root: Path) -> dict[str, Any]:
    config = read_yaml(root / "config" / "job_hunter.yml")

    resume_rel = _configured_profile_rel(config, "resume_tex", "profile/resume_double_column.tex")
    career_rel = _configured_profile_rel(config, "career_context", "profile/career_context.md")
    story_rel = _configured_profile_rel(config, "story_bank", "profile/story_bank.md")

    resume_path = root / resume_rel
    career_path = root / career_rel
    story_path = root / story_rel

    blocking = {
        "job_titles": bool(config.get("job_titles")),
        "experience_levels": bool(filter_values(config, "experience_levels")),
        "region": _has_enabled_region(config),
        "career_context": career_path.exists() and _career_context_filled(career_path),
        "base_resume": resume_path.exists() and _resume_filled(resume_path),
        "api_key": _api_key_configured(config),
    }

    non_blocking: list[str] = []
    if not (story_path.exists() and _has_final_story(story_path)):
        non_blocking.append("no_final_story")
    if not _workflow_schedule_configured(root):
        non_blocking.append("no_github_schedule")
    if not _browser_support_available():
        non_blocking.append("no_browser_support")
    if not _telemetry_healthy(root):
        non_blocking.append("missing_telemetry")

    return {
        "ready": all(blocking.values()),
        "blocking": blocking,
        "non_blocking": non_blocking,
    }


def _browser_support_available() -> bool:
    from job_hunter.sources.career_pages._rendering import is_chromium_installed

    return is_chromium_installed()


def _telemetry_healthy(root: Path) -> bool:
    from job_hunter.metrics.telemetry import telemetry_status

    return bool(telemetry_status(root)["collector_healthy"])
