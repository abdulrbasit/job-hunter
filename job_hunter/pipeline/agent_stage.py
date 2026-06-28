"""claude_agent_sdk wrapper for programmatic agent-mode stage execution.

Captures ResultMessage.usage (input/output/cached tokens) and total_cost_usd
so agent-mode runs produce the same token metrics as llm-api mode.

ponytail: wire into pipeline stages separately; this is the foundation only.
"""

from __future__ import annotations

import asyncio
from typing import Any

_SDK_AVAILABLE = False
try:
    import claude_agent_sdk as _sdk  # noqa: F401

    _SDK_AVAILABLE = True
except ImportError:
    pass


def run_agent_stage(
    prompt: str,
    *,
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
) -> tuple[str, dict[str, Any], float | None]:
    """Run a prompt via claude_agent_sdk, return (result_text, usage_dict, cost_usd).

    usage_dict keys: input_tokens, output_tokens, cache_read_input_tokens,
    cache_creation_input_tokens.  Returns ("", {}, None) if SDK not installed.
    """
    if not _SDK_AVAILABLE:
        return "", {}, None
    return asyncio.run(_query(prompt, allowed_tools=allowed_tools or [], system_prompt=system_prompt))


async def _query(
    prompt: str,
    *,
    allowed_tools: list[str],
    system_prompt: str | None,
) -> tuple[str, dict[str, Any], float | None]:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    opts = ClaudeAgentOptions(allowed_tools=allowed_tools)
    if system_prompt:
        opts.system_prompt = system_prompt  # type: ignore[attr-defined]

    result_text = ""
    usage: dict[str, Any] = {}
    cost: float | None = None
    async for msg in query(prompt=prompt, options=opts):
        if isinstance(msg, ResultMessage):
            result_text = msg.result or ""
            usage = msg.usage or {}
            cost = msg.total_cost_usd
    return result_text, usage, cost
