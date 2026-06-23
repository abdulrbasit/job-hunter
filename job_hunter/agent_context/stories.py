"""Story bank parsing helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from job_hunter.agent_context._types import RATING_RE, STORY_HEADING_RE, StoryBlock
from job_hunter.agent_context._utils import _clip, _read_yaml, _root


def _plain_summary(block: str) -> str:
    for raw in block.splitlines()[1:]:
        line = raw.strip()
        if not line or line.startswith("**Rating") or line.startswith("- **Tags"):
            continue
        line = re.sub(r"[*_`>#-]+", "", line).strip()
        if line:
            return _clip(line, 180)
    return ""


def _extract_tags(block: str) -> list[str]:
    for line in block.splitlines():
        if "Tags:" not in line:
            continue
        value = line.split("Tags:", 1)[1].strip(" *")
        return [tag.strip() for tag in value.split(",") if tag.strip()]
    return []


def _story_blocks(root: Path) -> list[StoryBlock]:
    profile = _read_yaml(root / "config" / "job_hunter.yml").get("profile", {})
    story_bank = Path(profile.get("story_bank", "profile/story_bank.md"))
    path = story_bank if story_bank.is_absolute() else root / story_bank
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    role = ""
    in_final = False
    current: list[str] = []
    current_id = ""
    current_title = ""
    current_role = ""
    stories: list[StoryBlock] = []

    def flush() -> None:
        nonlocal current, current_id, current_title, current_role
        if not current or not current_id:
            current = []
            return
        block = "\n".join(current).strip()
        rating_match = RATING_RE.search(block)
        stories.append(
            StoryBlock(
                story_id=current_id,
                title=current_title,
                role=current_role,
                rating=rating_match.group(1) if rating_match else "",
                tags=_extract_tags(block),
                summary=_plain_summary(block),
                text=block,
            )
        )
        current = []
        current_id = ""
        current_title = ""
        current_role = ""

    for line in lines:
        if line.startswith("# ") and not line.startswith("##"):
            flush()
            role = line[2:].strip()
            in_final = False
            continue
        if line.startswith("## "):
            flush()
            in_final = "Final" in line
            continue
        match = STORY_HEADING_RE.match(line) if in_final else None
        if match:
            flush()
            current_id = match.group(1)
            current_title = match.group(2)
            current_role = role
            current = [line]
            continue
        if current:
            current.append(line)
    flush()
    return stories


def story_index(*, root: Path | None = None) -> list[dict[str, Any]]:
    return [
        {
            "id": story.story_id,
            "title": story.title,
            "role": story.role,
            "rating": story.rating,
            "tags": story.tags,
            "summary": story.summary,
        }
        for story in _story_blocks(_root(root))
    ]


def story_by_id(story_id: str, *, root: Path | None = None) -> StoryBlock | None:
    normalized = story_id.strip().lower()
    for story in _story_blocks(_root(root)):
        if story.story_id.lower() == normalized:
            return story
    return None


def final_stories_text(*, root: Path | None = None) -> str:
    stories = _story_blocks(_root(root))
    if not stories:
        return "No Final STAR stories found."
    return "\n\n---\n\n".join(story.text for story in stories)
