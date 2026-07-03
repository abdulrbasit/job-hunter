import builtins
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from job_hunter.llm import client as real_llm_client
from job_hunter.llm.client import LLMClient


def _client_with_limit(requests_per_minute):
    client = LLMClient.__new__(LLMClient)
    client._provider = "test"
    client._raw = None
    client._rpm = requests_per_minute
    client._rate_lock = __import__("threading").Lock()
    client._timestamps = deque()
    return client


def test_throttle_noops_when_disabled(monkeypatch) -> None:
    client = _client_with_limit(0)
    sleep = MagicMock()
    monkeypatch.setattr("job_hunter.llm.client.time.sleep", sleep)

    client._throttle()

    sleep.assert_not_called()


def test_throttle_waits_when_window_is_full(monkeypatch) -> None:
    client = _client_with_limit(2)
    client._timestamps.extend([100.0, 101.0])
    sleep = MagicMock()
    times = iter([120.0, 160.1])
    monkeypatch.setattr("job_hunter.llm.client.time.monotonic", lambda: next(times))
    monkeypatch.setattr("job_hunter.llm.client.time.sleep", sleep)

    client._throttle()

    sleep.assert_called_once_with(40.0)
    assert list(client._timestamps) == [101.0, 160.1]


def test_get_llm_client_cache_is_thread_safe(monkeypatch) -> None:
    created = []
    config = {
        "llm": {
            "default_provider": "ollama",
            "providers": {"validation": "ollama"},
            "rate_limits": {"validation": {"requests_per_minute": 4}},
            "ollama": {"base_url": "http://localhost:11434"},
        },
    }

    class FakeClient:
        def __init__(self, provider, api_key="", base_url="", requests_per_minute=0) -> None:
            created.append((provider, api_key, base_url, requests_per_minute))

    monkeypatch.setattr("job_hunter.config.get_config", lambda _name: config)
    monkeypatch.setattr("job_hunter.config.get_secret", lambda *args, **kwargs: "")
    monkeypatch.setattr(real_llm_client, "LLMClient", FakeClient)
    monkeypatch.setattr(real_llm_client, "_cache", {})

    with ThreadPoolExecutor(max_workers=8) as executor:
        clients = list(executor.map(lambda _: real_llm_client.get_client("validation"), range(20)))

    assert len(created) == 1
    assert len({id(client) for client in clients}) == 1
    assert created == [("ollama", "", "http://localhost:11434", 4)]


def test_get_llm_client_applies_independent_rpm_per_role_on_same_provider(monkeypatch) -> None:
    created = {}
    config = {
        "llm": {
            "default_provider": "anthropic",
            "providers": {"scoring": "anthropic", "tailoring": "anthropic"},
            "rate_limits": {
                "scoring": {"requests_per_minute": 10},
                "tailoring": {"requests_per_minute": 60},
            },
        },
    }

    class FakeClient:
        def __init__(self, provider, api_key="", base_url="", requests_per_minute=0) -> None:
            self.provider = provider
            self.rpm = requests_per_minute

    monkeypatch.setattr("job_hunter.config.get_config", lambda _name: config)
    monkeypatch.setattr("job_hunter.config.get_secret", lambda *args, **kwargs: "")
    monkeypatch.setattr(real_llm_client, "LLMClient", FakeClient)
    monkeypatch.setattr(real_llm_client, "_cache", {})

    created["scoring"] = real_llm_client.get_client("scoring")
    created["tailoring"] = real_llm_client.get_client("tailoring")

    assert created["scoring"].rpm == 10
    assert created["tailoring"].rpm == 60
    assert created["scoring"] is not created["tailoring"]
    # Same provider, but role-scoped caching means calling scoring again returns
    # the same instance it already got — not tailoring's.
    assert real_llm_client.get_client("scoring") is created["scoring"]


def _client_for_call(provider):
    client = LLMClient.__new__(LLMClient)
    client._provider = provider
    client._raw = MagicMock()
    return client


class _Usage:
    def __init__(self):
        self.prompt_tokens = 1
        self.completion_tokens = 1
        self.input_tokens = 1
        self.output_tokens = 1


def test_openai_uses_json_response_mode_when_requested() -> None:
    client = _client_for_call("openai")
    resp = MagicMock()
    resp.choices[0].message.content = "{}"
    resp.usage = _Usage()
    client._raw.chat.completions.create.return_value = resp

    client._call(
        real_llm_client.LLMRequest(role="scoring", prompt="Return json", system=""),
        "gpt-5.4",
        100,
        False,
        "5m",
        response_format="json",
    )

    kwargs = client._raw.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}


def test_ollama_uses_json_response_mode_when_requested() -> None:
    client = _client_for_call("ollama")
    resp = MagicMock()
    resp.choices[0].message.content = "{}"
    resp.usage = _Usage()
    client._raw.chat.completions.create.return_value = resp

    client._call(
        real_llm_client.LLMRequest(role="scoring", prompt="Return json", system=""),
        "llama3",
        100,
        False,
        "5m",
        response_format="json",
    )

    kwargs = client._raw.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}


def test_openai_omits_response_format_when_not_requested() -> None:
    client = _client_for_call("openai")
    resp = MagicMock()
    resp.choices[0].message.content = "plain text"
    resp.usage = _Usage()
    client._raw.chat.completions.create.return_value = resp

    client._call(
        real_llm_client.LLMRequest(role="scoring", prompt="Hello", system=""), "gpt-5.4", 100, False, "5m", None
    )

    kwargs = client._raw.chat.completions.create.call_args.kwargs
    assert "response_format" not in kwargs


def test_openai_extracts_cached_tokens_from_prompt_tokens_details() -> None:
    """OpenAI auto-caches prompts >~1024 tokens and reports it via prompt_tokens_details —
    must be read, not hardcoded to 0."""
    client = _client_for_call("openai")
    resp = MagicMock()
    resp.choices[0].message.content = "plain text"
    usage = _Usage()
    usage.prompt_tokens_details = MagicMock(cached_tokens=5)
    resp.usage = usage
    client._raw.chat.completions.create.return_value = resp

    _text, _in_tok, _out_tok, cached = client._call(
        real_llm_client.LLMRequest(role="scoring", prompt="Hello", system=""), "gpt-5.4", 100, False, "5m", None
    )

    assert cached == 5


class _GoogleUsage:
    def __init__(self) -> None:
        self.prompt_token_count = 12
        self.candidates_token_count = 7
        self.cached_content_token_count = 3


def test_google_extracts_token_usage_from_usage_metadata() -> None:
    """google-genai responses carry real usage on resp.usage_metadata — was previously
    hardcoded to (0, 0, 0), silently undercounting cost for any role on provider: google."""
    client = _client_for_call("google")
    resp = MagicMock()
    resp.text = "hello"
    resp.usage_metadata = _GoogleUsage()
    client._raw.models.generate_content.return_value = resp

    _text, in_tok, out_tok, cached = client._call(
        real_llm_client.LLMRequest(role="scoring", prompt="Hi", system=""), "gemini-x", 100, False, "5m", None
    )

    assert (in_tok, out_tok, cached) == (12, 7, 3)


def test_google_reports_zero_tokens_when_usage_metadata_missing() -> None:
    client = _client_for_call("google")
    resp = MagicMock()
    resp.text = "hello"
    resp.usage_metadata = None
    client._raw.models.generate_content.return_value = resp

    _text, in_tok, out_tok, cached = client._call(
        real_llm_client.LLMRequest(role="scoring", prompt="Hi", system=""), "gemini-x", 100, False, "5m", None
    )

    assert (in_tok, out_tok, cached) == (0, 0, 0)


def test_anthropic_ignores_response_format_and_keeps_parse_repair_contract() -> None:
    """Anthropic has no native JSON mode — callers rely on parse_json_object/repair_json_object."""
    client = _client_for_call("anthropic")
    resp = MagicMock()
    resp.content = [MagicMock(text="{}")]
    resp.usage = _Usage()
    resp.usage.cache_read_input_tokens = 0
    client._raw.messages.create.return_value = resp

    client._call(
        real_llm_client.LLMRequest(role="scoring", prompt="Return json", system=""),
        "claude-sonnet-4-6",
        100,
        False,
        "5m",
        response_format="json",
    )

    kwargs = client._raw.messages.create.call_args.kwargs
    assert "response_format" not in kwargs


@pytest.mark.parametrize(
    ("provider", "blocked_import"),
    [("anthropic", "anthropic"), ("openai", "openai"), ("google", "google")],
)
def test_missing_provider_sdk_points_to_llm_extra(monkeypatch, provider, blocked_import) -> None:
    real_import = builtins.__import__

    def missing_sdk(name, *args, **kwargs):
        if name == blocked_import:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_sdk)
    client = LLMClient.__new__(LLMClient)

    with pytest.raises(ImportError, match="Reinstall job-hunter-kit"):
        client._init(provider, "", "")
