"""In-memory token accounting per pipeline role, for a single run."""

from __future__ import annotations

import threading

from job_hunter.llm.types import RoleName, TokenUsage

_token_totals: dict[str, dict[str, int]] = {}
_token_lock = threading.Lock()


def record_tokens(role: RoleName, usage: TokenUsage) -> None:
    with _token_lock:
        b = _token_totals.setdefault(role, {"in": 0, "out": 0, "cached": 0})
        b["in"] += usage.input_tokens
        b["out"] += usage.output_tokens
        b["cached"] += usage.cached_tokens


def get_token_totals() -> dict[str, dict[str, int]]:
    with _token_lock:
        return {k: dict(v) for k, v in _token_totals.items()}


def reset_token_totals() -> None:
    with _token_lock:
        _token_totals.clear()
