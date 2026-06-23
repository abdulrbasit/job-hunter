"""LLM-assisted job search — public API for AI-backed title+region discovery.

Sends prompts to an LLM provider asking it to return real job URLs matching
the configured titles and regions. Gated by `sources.llm_search.enabled` in
config/job_hunter.yml and only fires when the board+ATS yield falls below
the trigger_threshold.
"""

from __future__ import annotations

from job_hunter.sources.ai_web_search import fetch_ai_web_search_jobs

__all__ = [
    "fetch_ai_web_search_jobs",
]
