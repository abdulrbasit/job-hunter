"""Evidence context — universal no-fabrication writing rules for content skills."""

from __future__ import annotations

from typing import Any

from job_hunter.writing.rules import universal_evidence_rules


def evidence_context() -> dict[str, Any]:
    """Universal evidence rules — the same source llm-api mode would use."""
    return {"writing_rules": {"evidence": list(universal_evidence_rules())}}
