"""Story bank parsing helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from job_hunter.agent_context._types import RATING_RE, STORY_HEADING_RE, StoryBlock
from job_hunter.agent_context._utils import _clip, _prefer_compiled, _root
from job_hunter.core.utils import read_yaml

_STOPWORDS = frozenset(
    """
    the and for with this that from into your our their its will are was were has have had
    you they them then than not but out over under about who what when where how why
    role team work working across ability strong experience years including etc job jobs
    """.split()
)


def _tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#]+", text.lower()) if len(w) > 2 and w not in _STOPWORDS}


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
    profile = read_yaml(root / "config" / "job_hunter.yml").get("profile", {})
    story_bank = Path(profile.get("story_bank", "profile/story_bank.md"))
    path = story_bank if story_bank.is_absolute() else root / story_bank
    path = _prefer_compiled(path, root)
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


def match_stories(*, job: str, root: Path | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Rank Final stories by deterministic keyword overlap with a job's JD text and matched
    score keywords, so the agent starts from a short pre-filtered candidate list instead of
    scanning the full story index. Final selection is still the agent's judgment call."""
    base = _root(root)
    stories = _story_blocks(base)
    if not stories:
        return []

    folder = base / "outputs" / "jobs" / job
    jd_text = (folder / "jd.md").read_text(encoding="utf-8") if (folder / "jd.md").exists() else ""
    score = read_yaml(folder / "score.yml") if (folder / "score.yml").exists() else {}
    keywords = list(score.get("matched", score.get("matched_keywords", [])))
    jd_tokens = _tokenize(jd_text) | _tokenize(" ".join(keywords))
    if not jd_tokens:
        return []

    ranked: list[dict[str, Any]] = []
    for story in stories:
        story_tokens = _tokenize(" ".join(story.tags)) | _tokenize(story.title) | _tokenize(story.summary)
        overlap = sorted(jd_tokens & story_tokens)
        if not overlap:
            continue
        ranked.append({"id": story.story_id, "title": story.title, "score": len(overlap), "matched_terms": overlap})

    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:limit]


def final_stories_text(*, root: Path | None = None) -> str:
    stories = _story_blocks(_root(root))
    if not stories:
        return "No Final STAR stories found."
    return "\n\n---\n\n".join(story.text for story in stories)
