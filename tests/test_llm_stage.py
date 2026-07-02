"""Tests for llm/stage.py — LLMStage in isolation."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from job_hunter.llm.stage import LLMStage


@dataclass
class _FakeSettings:
    model: str = "test-model"
    max_tokens: int = 512


def _stage(response: str = '{"result": "ok"}', *, role: str = "scoring") -> tuple[LLMStage, MagicMock]:
    client = MagicMock()
    client.complete.return_value = MagicMock(content=response)
    stage = LLMStage(
        role=role,
        client_factory=lambda _: client,
        settings_factory=lambda *_a, **_kw: _FakeSettings(),
    )
    return stage, client


def test_complete_calls_client_with_model_and_max_tokens() -> None:
    stage, client = _stage()

    stage.complete(system="sys", user="usr")

    client.complete.assert_called_once()
    _, kwargs = client.complete.call_args
    assert kwargs["model"] == "test-model"
    assert kwargs["max_tokens"] == 512


def test_complete_returns_content_string() -> None:
    stage, _ = _stage(response="tailored LaTeX here")

    result = stage.complete(system="sys", user="usr")

    assert result == "tailored LaTeX here"


def test_parse_json_object_happy_path() -> None:
    raw = '{"score": 85, "gaps": []}'

    result = LLMStage.parse_json_object(raw, "bad parse")

    assert result == {"score": 85, "gaps": []}


def test_parse_json_object_raises_on_non_dict() -> None:
    with pytest.raises(ValueError, match="not a dict"):
        LLMStage.parse_json_object("[1, 2, 3]", "not a dict")


def test_parse_json_object_raises_on_malformed_syntax() -> None:
    import json as _json

    with pytest.raises(_json.JSONDecodeError):
        LLMStage.parse_json_object('{"score": 85, "gaps": [}', "bad parse")


def test_malformed_response_is_recovered_via_repair_fallback() -> None:
    """Mirrors pipeline/stages/scoring.py's parse -> except -> repair pattern."""
    import json as _json

    stage, client = _stage()
    raw = '{"score": 85, "gaps": [}'  # truncated/invalid JSON
    client.complete.return_value = MagicMock(content='{"score": 85, "gaps": []}')

    try:
        result = stage.parse_json_object(raw, "scoring response must be a JSON object")
    except (_json.JSONDecodeError, ValueError):
        result = stage.repair_json_object(
            system="sys",
            raw=raw,
            repair_prompt="Fix this JSON: {raw}",
            max_chars=4000,
            error_message="scoring response must be a JSON object",
        )

    assert result == {"score": 85, "gaps": []}


def test_repair_json_object_calls_complete_with_formatted_prompt() -> None:
    repaired = '{"score": 70}'
    stage, client = _stage(response=repaired)
    client.complete.return_value = MagicMock(content=repaired)

    result = stage.repair_json_object(
        system="sys",
        raw="bad json here",
        repair_prompt="Fix this: {raw}",
        max_chars=100,
        error_message="bad",
    )

    assert result == {"score": 70}
    call_kwargs = client.complete.call_args
    req = call_kwargs[0][0]
    assert "bad json here" in req.prompt


def test_repair_json_object_truncates_raw_at_max_chars() -> None:
    stage, client = _stage(response='{"x": 1}')
    client.complete.return_value = MagicMock(content='{"x": 1}')
    long_raw = "A" * 200

    stage.repair_json_object(
        system="sys",
        raw=long_raw,
        repair_prompt="Fix: {raw}",
        max_chars=10,
        error_message="bad",
    )

    req = client.complete.call_args[0][0]
    assert "A" * 11 not in req.prompt
    assert "A" * 10 in req.prompt


def test_stage_passes_cache_settings_to_client() -> None:
    stage, client = _stage()
    stage_cached = LLMStage(
        role="tailoring",
        cache_system=True,
        cache_ttl="1h",
        client_factory=lambda _: client,
        settings_factory=lambda *_a, **_kw: _FakeSettings(),
    )
    client.complete.return_value = MagicMock(content="ok")

    stage_cached.complete(system="sys", user="usr")

    _, kwargs = client.complete.call_args
    assert kwargs["cache_system"] is True
    assert kwargs["cache_ttl"] == "1h"
