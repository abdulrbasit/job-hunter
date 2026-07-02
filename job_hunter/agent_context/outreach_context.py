"""Outreach context — universal outreach writing rules for the outreach skill."""

from __future__ import annotations

from typing import Any

from job_hunter.writing.rules import universal_outreach_rules


def outreach_context() -> dict[str, Any]:
    """Universal outreach rules — the same source llm-api mode would use."""
    return {"writing_rules": {"outreach": list(universal_outreach_rules())}}
