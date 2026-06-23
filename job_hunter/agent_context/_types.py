"""Shared types and constants for agent_context sub-modules."""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_SNIPPET_CHARS = 700
MAX_JD_CHARS = 6000
DEFAULT_QUEUE_PATH = "outputs/state/agent_candidate_queue.json"
DEFAULT_CANDIDATE_SCOPE = "briefing-backlog"
JD_LIFECYCLE_IMPORT_STATUSES = {"thin", "fetch_failed", "page_noise"}
STORY_HEADING_RE = re.compile(r"^###\s+([A-Za-z0-9]+-\d+)\s+[—-]\s+(.+?)\s*$")
RATING_RE = re.compile(r"Rating:\s*([0-9]+(?:\.[0-9]+)?/10)")


@dataclass(frozen=True)
class StoryBlock:
    story_id: str
    title: str
    role: str
    rating: str
    tags: list[str]
    summary: str
    text: str
