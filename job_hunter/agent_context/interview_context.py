"""Interview-prep context — bounded job + matched-story data for the interview skill."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from job_hunter.agent_context._types import MAX_JD_CHARS
from job_hunter.agent_context._utils import _root
from job_hunter.agent_context.score_context import _read_job_folder
from job_hunter.agent_context.stories import match_stories
from job_hunter.writing.rules import universal_evidence_rules


def interview_context(job: str, root: Path | None = None, max_jd_chars: int = MAX_JD_CHARS) -> dict[str, Any]:
    """Bounded job + matched-story context for interview question generation.

    `job.score.matched_story_ids` (selected during scoring) is the primary story source;
    `matched_stories` is a JD-keyword-ranked fallback shortlist.
    """
    base = _root(root)
    return {
        "job": _read_job_folder(base, job, max_jd_chars),
        "matched_stories": match_stories(job=job, root=base),
        "writing_rules": {"evidence": list(universal_evidence_rules())},
        "required_outputs": [
            {"path": f"outputs/jobs/{job}/interview_prep.md", "format": "markdown"},
        ],
    }
