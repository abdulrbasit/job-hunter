"""LLM response text parsing helpers."""

from __future__ import annotations

import re


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
