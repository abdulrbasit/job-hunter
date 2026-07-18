"""Agent context package — bounded context builders for Claude Code skills."""

from job_hunter.agent_context.batch import (
    apply_screen_judgment,
    build_candidate_batch,
    discard_screened_candidates,
    screen_candidate_batch,
)
from job_hunter.agent_context.briefing import linkedin_weekly_context
from job_hunter.agent_context.candidates import build_candidate_queue, candidate_from_queue
from job_hunter.agent_context.evidence_context import evidence_context
from job_hunter.agent_context.interview_context import interview_context
from job_hunter.agent_context.lifecycle import candidate_lifecycle, validate_score_file
from job_hunter.agent_context.outreach_context import outreach_context
from job_hunter.agent_context.score_context import profile_context, score_context
from job_hunter.agent_context.stories import final_stories_text, match_stories, story_by_id, story_index
from job_hunter.agent_context.tailor_context import tailor_context

__all__ = [
    "apply_screen_judgment",
    "build_candidate_batch",
    "build_candidate_queue",
    "candidate_from_queue",
    "candidate_lifecycle",
    "discard_screened_candidates",
    "evidence_context",
    "final_stories_text",
    "interview_context",
    "linkedin_weekly_context",
    "match_stories",
    "outreach_context",
    "profile_context",
    "score_context",
    "screen_candidate_batch",
    "story_by_id",
    "story_index",
    "tailor_context",
    "validate_score_file",
]
