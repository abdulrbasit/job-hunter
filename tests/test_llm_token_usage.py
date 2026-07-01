"""Tests for llm/token_usage.py — per-role token accounting."""

from __future__ import annotations

from job_hunter.llm.token_usage import get_token_totals, record_tokens, reset_token_totals
from job_hunter.llm.types import TokenUsage


def setup_function() -> None:
    reset_token_totals()


def test_record_tokens_accumulates_per_role() -> None:
    record_tokens("scoring", TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=2))
    record_tokens("scoring", TokenUsage(input_tokens=3, output_tokens=1, cached_tokens=0))

    totals = get_token_totals()

    assert totals["scoring"] == {"in": 13, "out": 6, "cached": 2}


def test_record_tokens_keeps_roles_independent() -> None:
    record_tokens("scoring", TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=0))
    record_tokens("tailoring", TokenUsage(input_tokens=20, output_tokens=8, cached_tokens=0))

    totals = get_token_totals()

    assert totals["scoring"]["in"] == 10
    assert totals["tailoring"]["in"] == 20


def test_reset_token_totals_clears_state() -> None:
    record_tokens("scoring", TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=0))

    reset_token_totals()

    assert get_token_totals() == {}


def test_get_token_totals_returns_a_copy() -> None:
    record_tokens("scoring", TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=0))

    totals = get_token_totals()
    totals["scoring"]["in"] = 999

    assert get_token_totals()["scoring"]["in"] == 10
