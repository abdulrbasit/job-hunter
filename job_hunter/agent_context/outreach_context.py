"""Outreach context — universal outreach rules, plus bounded job/story context when scoped."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from job_hunter.agent_context._types import MAX_JD_CHARS
from job_hunter.agent_context._utils import _root
from job_hunter.agent_context.score_context import _read_job_folder
from job_hunter.agent_context.stories import match_stories
from job_hunter.writing.rules import universal_outreach_rules


def outreach_context(
    job: str | None = None, root: Path | None = None, max_jd_chars: int = MAX_JD_CHARS
) -> dict[str, Any]:
    """Universal outreach rules; adds bounded job + matched-story context when `job` is given."""
    payload: dict[str, Any] = {"writing_rules": {"outreach": list(universal_outreach_rules())}}
    if not job:
        return payload
    base = _root(root)
    payload["job"] = _read_job_folder(base, job, max_jd_chars)
    payload["matched_stories"] = match_stories(job=job, root=base)
    payload["required_outputs"] = [
        {"path": f"outputs/jobs/{job}/outreach_drafts.md", "format": "markdown"},
    ]
    return payload
