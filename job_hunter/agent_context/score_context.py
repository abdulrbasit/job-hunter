"""Score context helpers for agent scoring workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from job_hunter.agent_context._types import MAX_JD_CHARS
from job_hunter.agent_context._utils import _clip, _prefer_compiled, _read_json_or_yaml, _root
from job_hunter.agent_context.candidates import candidate_from_queue
from job_hunter.agent_context.stories import match_stories, story_index
from job_hunter.config.reference_data import resolve_max_years_experience, student_mode
from job_hunter.core.posting_types import evidence_scoring_guidance
from job_hunter.core.utils import read_yaml
from job_hunter.filters import filter_values
from job_hunter.writing.rules import universal_score_decision_rules


def _profile_context(root: Path) -> dict[str, Any]:
    config = read_yaml(root / "config" / "job_hunter.yml")
    scoring = config.get("scoring", {})
    profile = config.get("profile", {})
    configured_context = Path(profile.get("career_context", "profile/career_context.md"))
    context_path = configured_context if configured_context.is_absolute() else root / configured_context
    context_path = _prefer_compiled(context_path, root)
    career_context = context_path.read_text(encoding="utf-8") if context_path.exists() else ""
    resume_value = str(profile.get("resume_tex") or "")
    resume_path = None
    if resume_value:
        configured_resume = Path(resume_value)
        resume_path = configured_resume if configured_resume.is_absolute() else root / configured_resume

    # Prefer pre-compiled compact text for scoring; fall back to raw .tex
    compact_resume = root / "outputs" / "state" / "compiled" / "resume.compact.txt"
    if compact_resume.exists():
        resume_tex = compact_resume.read_text(encoding="utf-8")
    elif resume_path and resume_path.exists():
        resume_tex = resume_path.read_text(encoding="utf-8")
    else:
        resume_tex = ""

    return {
        "student_mode": student_mode(config),
        "scoring_guidance": evidence_scoring_guidance(is_student=student_mode(config)),
        "scoring": {
            "min_fit_score": scoring.get("min_fit_score"),
            # Resolved, not raw: an unset value defaults to the selected experience_levels'
            # derived cap (see resolve_max_years_experience) rather than showing the agent a null.
            "max_years_experience_required": resolve_max_years_experience(config),
        },
        "excluded_industries": filter_values(config, "excluded_industries"),
        "target_titles": config.get("job_titles", []),
        "career_context": _clip(career_context, 2000),
        "resume_tex": _clip(resume_tex, 6000),
    }


def profile_context(root: Path | None = None) -> dict[str, Any]:
    """Public entry point for `agent-context profile` — the same profile block score_context
    embeds, fetched once per batch run instead of once per job (see score_context's
    include_profile parameter)."""
    return _profile_context(_root(root))


def _read_job_folder(root: Path, slug: str, max_jd_chars: int) -> dict[str, Any]:
    folder = root / "outputs" / "jobs" / slug
    meta = _read_json_or_yaml(folder / "meta.json") if (folder / "meta.json").exists() else {}
    jd = (folder / "jd.md").read_text(encoding="utf-8") if (folder / "jd.md").exists() else ""
    score = read_yaml(folder / "score.yml")
    return {
        "slug": slug,
        "meta": meta,
        "score": score,
        "jd_excerpt": _clip(jd, max_jd_chars),
        "jd_chars": len(jd),
    }


def score_context(
    *,
    mode: str,
    root: Path | None = None,
    job: str = "",
    queue: Path | None = None,
    index: int = 1,
    candidate_id: str = "",
    max_jd_chars: int = MAX_JD_CHARS,
    include_profile: bool = True,
) -> dict[str, Any]:
    base = _root(root)
    payload: dict[str, Any] = {
        "mode": mode,
        "profile": (
            _profile_context(base)
            if include_profile
            else "omitted — already fetched once this run via `agent-context profile`"
        ),
        "story_policy": (
            "snippet mode uses no story bank; full mode starts with matched_stories as a "
            "keyword-ranked shortlist, may use story-index or stories-final for broader "
            "verified-evidence comparison, then records selected story IDs."
        ),
    }
    if mode == "snippet":
        if not queue:
            raise ValueError("snippet mode requires --queue")
        payload["candidate"] = candidate_from_queue(queue, index, candidate_id=candidate_id)
        payload["story_index"] = []
        return payload
    if mode == "full":
        if not job:
            raise ValueError("full mode requires --job")
        payload["job"] = _read_job_folder(base, job, max_jd_chars)
        payload["story_index"] = story_index(root=base)
        payload["matched_stories"] = match_stories(job=job, root=base)
        payload["decision_rules"] = list(universal_score_decision_rules())
        payload["required_outputs"] = [
            {
                "path": f"outputs/jobs/{job}/score.yml",
                "format": "yaml",
                "validate_with": "job-hunter internal agent-context validate-score",
            },
            {"path": f"outputs/jobs/{job}/evaluation.md", "format": "markdown"},
        ]
        return payload
    raise ValueError("mode must be snippet or full")
