"""Derived runtime config: API settings, timeouts, and execution mode."""

from __future__ import annotations

from functools import cache
from typing import Any, Literal, cast

from job_hunter.config.defaults import HTTP_DEFAULTS
from job_hunter.config.loader import get_job_hunter_config

_TIMEOUT_DEFAULTS: dict[str, int] = {
    "ats_scraper": 10,
    "playwright": 10,
    "job_boards": 15,
    "search_providers": 10,
    "jd_fetcher": 10,
}


@cache
def get_api_config() -> dict[str, Any]:
    """Return code-owned API/runtime settings with user LLM settings merged in."""
    config = get_job_hunter_config()
    llm = config.get("llm", {}) or {}
    return {
        "llm": {
            "provider": llm.get("default_provider", "anthropic"),
            "default_provider": llm.get("default_provider", "anthropic"),
            "providers": llm.get("providers", {}) or {},
            "models": llm.get("models", {}) or {},
            "max_tokens": llm.get("max_tokens", {}) or {},
            "max_workers": int(llm.get("max_workers", 5) or 5),
            "rate_limits": llm.get("rate_limits", {}) or {},
            "ollama": llm.get("ollama", {}) or {},
        },
        "http": HTTP_DEFAULTS,
        "profile": config.get("profile", {}) or {},
    }


def get_timeout(section: str) -> int:
    """Return timeout_seconds for a given HTTP section from code defaults."""
    configured = get_api_config().get("http", {}).get(section, {}).get("timeout_seconds")
    if configured is not None:
        return int(configured)
    if section in _TIMEOUT_DEFAULTS:
        return _TIMEOUT_DEFAULTS[section]
    raise KeyError(f"No timeout default for section: {section}")


def get_mode() -> Literal["agent", "llm-api"]:
    """Return the execution mode from config/job_hunter.yml."""
    raw = get_job_hunter_config().get("mode", "agent")
    if raw not in ("agent", "llm-api"):
        raise ValueError(f"Invalid mode '{raw}' in job_hunter.yml; must be agent or llm-api")
    return cast(Literal["agent", "llm-api"], raw)
