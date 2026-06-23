"""LLM response parsing and role-setting helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass


def extract_json_object(text: str) -> str:
    """Extract the first JSON object or array from LLM response text.

    Handles markdown code fences (```json ... ```) and bare JSON.
    Returns the raw JSON string for the caller to parse, or the original
    text if no JSON structure is found.
    """
    if not text:
        return "{}"

    # Strip markdown code fence
    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", text)
    if fence_match:
        return fence_match.group(1).strip()

    # Try whichever opening bracket appears first in the text
    pos_obj = text.find("{")
    pos_arr = text.find("[")
    if pos_arr != -1 and (pos_obj == -1 or pos_arr < pos_obj):
        pairs = (("[", "]"), ("{", "}"))
    else:
        pairs = (("{", "}"), ("[", "]"))

    for start_char, end_char in pairs:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

    return text


@dataclass
class LLMRoleSettings:
    provider: str
    model: str
    max_tokens: int


def get_llm_role_settings(role: str, *, api_cfg: dict | None = None) -> LLMRoleSettings:
    """Return model, max_tokens, and provider for a pipeline role from job_hunter.yml."""
    if api_cfg is None:
        from job_hunter.config.loader import get_config

        api_cfg = get_config("job_hunter")

    llm = api_cfg.get("llm", {})
    provider = llm.get("providers", {}).get(role) or llm.get("default_provider", "anthropic")
    models = llm.get("models", {})
    if role not in models:
        raise KeyError(f"llm.models.{role}")
    max_tokens_cfg = llm.get("max_tokens", {})
    model = models[role]
    max_tokens = int(max_tokens_cfg.get(role, 1000))

    return LLMRoleSettings(provider=provider, model=model, max_tokens=max_tokens)
