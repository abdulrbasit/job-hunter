"""LLM package — provider-agnostic client and routing.

Usage:
    from job_hunter.llm import call, get_client
"""

from job_hunter.llm.client import call, get_client

__all__ = ["get_client", "call"]
