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
            "rate_limits": {"ollama": {"requests_per_minute": 4}},
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

    with pytest.raises(ImportError, match=r"job-hunter-kit\[llm\]"):
        client._init(provider, "", "")
