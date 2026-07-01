"""Pre-built tailoring + cover-letter constraints for agent skills.

Exposes the same config-driven rules that tailorer.py and cover_writer.py build before
each LLM call so agent mode applies identical constraints to llm-api mode.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from job_hunter.agent_context._utils import _root
from job_hunter.core.utils import read_yaml


def _score(root: Path, job: str) -> dict[str, Any]:
    path = root / "outputs" / "jobs" / job / "score.yml"
    if not path.exists():
        raise FileNotFoundError(f"score.yml not found: {path}")
    return read_yaml(path)


def _cover_constraints(cover_config: dict[str, Any]) -> dict[str, Any]:
    tone = cover_config.get("tone", []) or []
    content = cover_config.get("content", {}) or {}
    forbidden = cover_config.get("forbidden", {}) or {}
    structure = cover_config.get("structure", {}) or {}
    paragraphs = int(content.get("paragraphs", 4))
    return {
        "tone": ", ".join(tone) if tone else "formal, confident, and substantive",
        "target_words": int(content.get("target_words", 220)),
        "max_words": int(content.get("max_words", 280)),
        "paragraphs": paragraphs,
        "forbidden_phrases": list(forbidden.get("phrases", []) or []),
        "style_rules": list(forbidden.get("style", []) or []),
        "paragraph_structure": [
            {
                "index": i,
                "name": (structure.get(f"paragraph_{i}") or {}).get("name", f"Paragraph {i}"),
                "max_sentences": (structure.get(f"paragraph_{i}") or {}).get("max_sentences", 3),
                "purpose": (structure.get(f"paragraph_{i}") or {}).get("purpose", ""),
            }
            for i in range(1, paragraphs + 1)
        ],
    }


def tailor_context(job: str, root: Path | None = None) -> dict[str, Any]:
    """Pre-build tailoring + cover constraints from config for agent consumption."""
    from job_hunter.config.loader import get_config
    from job_hunter.pipeline.tailorer import (
        _build_positioning_rules,
        _build_project_rules,
        _build_tailoring_rules,
        _load_profile_text,
    )

    base = _root(root)
    config = get_config("job_hunter")
    score = _score(base, job)

    base_tex = _load_profile_text("resume_tex", "resume.tex")
    stories_config = (config.get("tailoring") or {}).get("stories") or {}
    story_bank = _load_profile_text("story_bank", stories_config.get("story_bank", "story_bank.md"))

    return {
        "keywords": list(score.get("matched", score.get("matched_keywords", []))),
        "gaps": list(score.get("gaps", [])),
        "tailoring_rules": _build_tailoring_rules(config),
        "positioning_rules": _build_positioning_rules(config),
        "project_rules": _build_project_rules(config, base_tex, story_bank),
        "cover_constraints": _cover_constraints(config.get("cover_letter") or {}),
    }
