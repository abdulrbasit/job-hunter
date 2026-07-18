"""Shared types and constants for agent_context sub-modules."""

from __future__ import annotations

import re

from job_hunter.models import StoryBlock as StoryBlock

MAX_SNIPPET_CHARS = 500
MAX_JD_CHARS = 3000
DEFAULT_QUEUE_PATH = "outputs/state/agent_candidate_queue.json"
DEFAULT_CANDIDATE_SCOPE = "briefing-backlog"
JD_LIFECYCLE_IMPORT_STATUSES = {"thin", "fetch_failed", "page_noise"}
STORY_HEADING_RE = re.compile(r"^###\s+([A-Za-z0-9]+-\d+)\s+[—-]\s+(.+?)\s*$")
RATING_RE = re.compile(r"Rating:\s*([0-9]+(?:\.[0-9]+)?/10)")
