"""Agent context package — bounded context builders for Claude Code skills."""

from job_hunter.agent_context.batch import build_candidate_batch, screen_candidate_batch
from job_hunter.agent_context.briefing import brief_context, linkedin_weekly_context
from job_hunter.agent_context.candidates import build_candidate_queue, candidate_from_queue
from job_hunter.agent_context.lifecycle import candidate_lifecycle, validate_score_file
from job_hunter.agent_context.score_context import score_context
from job_hunter.agent_context.stories import final_stories_text, story_by_id, story_index
from job_hunter.agent_context.tailor_context import tailor_context

__all__ = [
    "brief_context",
    "build_candidate_batch",
    "build_candidate_queue",
    "candidate_from_queue",
    "candidate_lifecycle",
    "final_stories_text",
    "linkedin_weekly_context",
    "score_context",
    "screen_candidate_batch",
    "story_by_id",
    "story_index",
    "tailor_context",
    "validate_score_file",
]
