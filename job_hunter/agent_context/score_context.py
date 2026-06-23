"""Score context helpers for agent scoring workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from job_hunter.agent_context._types import MAX_JD_CHARS
from job_hunter.agent_context._utils import _clip, _read_json_or_yaml, _read_yaml, _root
from job_hunter.agent_context.candidates import candidate_from_queue
from job_hunter.agent_context.stories import story_index


def _profile_context(root: Path) -> dict[str, Any]:
    config = _read_yaml(root / "config" / "job_hunter.yml")
    scoring = config.get("scoring", {})
    profile = config.get("profile", {})
    configured_context = Path(profile.get("career_context", "profile/career_context.md"))
    context_path = configured_context if configured_context.is_absolute() else root / configured_context
    career_context = context_path.read_text(encoding="utf-8") if context_path.exists() else ""
    return {
        "scoring": {
            "min_fit_score": scoring.get("min_fit_score"),
            "max_years_experience_required": scoring.get("max_years_experience_required"),
            "strategic_overrides": scoring.get("strategic_overrides", []),
        },
        "target_titles": config.get("job_titles", []),
        "career_context": _clip(career_context, 2000),
    }


def _read_job_folder(root: Path, slug: str, max_jd_chars: int) -> dict[str, Any]:
    folder = root / "outputs" / "jobs" / slug
    meta = _read_json_or_yaml(folder / "meta.json") if (folder / "meta.json").exists() else {}
    jd = (folder / "jd.md").read_text(encoding="utf-8") if (folder / "jd.md").exists() else ""
    score = _read_yaml(folder / "score.yml")
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
) -> dict[str, Any]:
    base = _root(root)
    payload: dict[str, Any] = {
        "mode": mode,
        "profile": _profile_context(base),
        "story_policy": (
            "snippet mode uses no story bank; full mode starts with story-index, "
            "may use stories-final for broad verified-evidence comparison, then records selected story IDs."
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
        return payload
    raise ValueError("mode must be snippet or full")
