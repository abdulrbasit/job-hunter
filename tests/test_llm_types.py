"""Tests for llm/types.py — LLM contracts."""

from __future__ import annotations

from job_hunter.llm.types import LLMRequest, LLMResponse, ModelConfig, TokenUsage


def test_llm_response_defaults() -> None:
    resp = LLMResponse(content="hi", provider="anthropic", model="claude")

    assert resp.input_tokens == 0
    assert resp.output_tokens == 0
    assert resp.cached_tokens == 0


def test_llm_request_role_and_prompt_required() -> None:
    req = LLMRequest(role="scoring", prompt="score this")

    assert req.role == "scoring"
    assert req.system is None


def test_token_usage_defaults_to_zero() -> None:
    usage = TokenUsage()

    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cached_tokens == 0


def test_model_config_holds_role_provider_model() -> None:
    config = ModelConfig(role="tailoring", provider="anthropic", model="claude-x", max_tokens=1000)

    assert config.role == "tailoring"
    assert config.provider == "anthropic"
    assert config.model == "claude-x"
    assert config.max_tokens == 1000
