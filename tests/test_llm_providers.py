"""Tests for llm/providers.py — provider selection and model routing."""

from __future__ import annotations

import pytest

from job_hunter.llm.providers import resolve_model_config, resolve_provider


def test_resolve_provider_uses_role_override() -> None:
    llm_cfg = {"default_provider": "anthropic", "providers": {"tailoring": "openai"}}

    assert resolve_provider("tailoring", llm_cfg) == "openai"


def test_resolve_provider_falls_back_to_default() -> None:
    llm_cfg = {"default_provider": "anthropic", "providers": {}}

    assert resolve_provider("scoring", llm_cfg) == "anthropic"


def test_resolve_provider_defaults_to_anthropic_when_unset() -> None:
    assert resolve_provider("scoring", {}) == "anthropic"


def test_resolve_model_config_uses_config_values() -> None:
    config = resolve_model_config(
        "validation",
        api_cfg={
            "llm": {
                "models": {"validation": "configured-model"},
                "max_tokens": {"validation": 123},
            }
        },
    )

    assert config.role == "validation"
    assert config.model == "configured-model"
    assert config.max_tokens == 123
    assert config.provider == "anthropic"


def test_resolve_model_config_requires_explicit_role_keys() -> None:
    with pytest.raises(KeyError, match="llm.models.jd_extraction"):
        resolve_model_config(
            "jd_extraction",
            api_cfg={"llm": {"models": {}, "max_tokens": {}}},
        )


def test_resolve_model_config_uses_default_provider_without_default_model() -> None:
    config = resolve_model_config(
        "scoring",
        api_cfg={
            "llm": {
                "default_provider": "ollama",
                "models": {"scoring": "local-model"},
                "max_tokens": {"scoring": 999},
            }
        },
    )

    assert config.provider == "ollama"
    assert config.model == "local-model"
