"""Provider-agnostic LLM client.

Supported providers: anthropic | openai | google | ollama

Configure per role in config/job_hunter.yml:

  llm:
    default_provider: anthropic
    providers:
      scoring: anthropic
      tailoring: openai
    models:
      scoring: your-scoring-model
      tailoring: your-tailoring-model
    max_tokens:
      scoring: 1000
      tailoring: 4000
    rate_limits:
      scoring: {requests_per_minute: 10}
      tailoring: {requests_per_minute: 60}

Call via call(role, prompt, system) — never instantiate LLMClient directly.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from job_hunter.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)
_LLM_EXTRA_HELP = "Reinstall job-hunter-kit to restore bundled LLM provider SDKs."


def _compress_request(prompt: str, system: str, model: str) -> tuple[str, str]:
    """Compress prompt and system context via headroom before sending to the LLM."""
    try:
        from headroom import compress  # noqa: PLC0415
    except ImportError:
        return prompt, system
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    compressed = compress(messages, model=model)
    c_system = next((m["content"] for m in compressed if m.get("role") == "system"), system)
    c_prompt = next((m["content"] for m in compressed if m.get("role") == "user"), prompt)
    return c_prompt, c_system


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate" in msg or "unavailable" in msg


class LLMClient:
    """Thin facade over provider SDKs. SDKs are lazily imported."""

    def __init__(self, provider: str, api_key: str = "", base_url: str = "", requests_per_minute: int = 0) -> None:
        self._provider = provider
        self._rpm = max(0, requests_per_minute)
        self._rate_lock = threading.Lock()
        self._timestamps: deque[float] = deque()
        self._raw = self._init(provider, api_key, base_url)

    def _init(self, provider: str, api_key: str, base_url: str) -> Any:
        if provider == "anthropic":
            try:
                from anthropic import Anthropic
            except ImportError:
                raise ImportError(_LLM_EXTRA_HELP) from None
            return Anthropic(api_key=api_key)

        if provider == "openai":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(_LLM_EXTRA_HELP) from None
            return OpenAI(api_key=api_key)

        if provider == "google":
            try:
                from google import genai
            except ImportError:
                raise ImportError(_LLM_EXTRA_HELP) from None
            return genai.Client(api_key=api_key)

        if provider == "ollama":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(_LLM_EXTRA_HELP) from None
            return OpenAI(base_url=base_url or "http://localhost:11434/v1", api_key="ollama")

        raise ValueError(f"Unknown provider: {provider!r}. Supported: anthropic | openai | google | ollama")

    def complete(
        self,
        req: LLMRequest,
        model: str,
        max_tokens: int,
        cache_system: bool = False,
        cache_ttl: str = "5m",
        response_format: str | None = None,
    ) -> LLMResponse:
        """Send a request and return a structured LLMResponse."""
        logger.debug("[llm] provider=%s model=%s max_tokens=%d", self._provider, model, max_tokens)
        compressed_prompt, compressed_system = _compress_request(req.prompt, req.system or "", model)
        req = LLMRequest(role=req.role, prompt=compressed_prompt, system=compressed_system or None)
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                self._throttle()
                content, in_tok, out_tok, cached = self._call(
                    req, model, max_tokens, cache_system, cache_ttl, response_format
                )
                return LLMResponse(
                    content=content,
                    provider=self._provider,
                    model=model,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cached_tokens=cached,
                )
            except Exception as exc:
                if not _is_retryable(exc) or attempt == 3:
                    raise
                delay = 2**attempt
                logger.warning("[llm] retryable error (attempt %d/3), retrying in %ds: %s", attempt, delay, exc)
                time.sleep(delay)
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("[llm] provider call failed without an exception")

    def _throttle(self) -> None:
        if self._rpm <= 0:
            return
        window = 60.0
        while True:
            with self._rate_lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= window:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._rpm:
                    self._timestamps.append(now)
                    return
                wait = window - (now - self._timestamps[0])
            time.sleep(max(wait, 0.1))

    def _call(
        self,
        req: LLMRequest,
        model: str,
        max_tokens: int,
        cache_system: bool,
        cache_ttl: str,
        response_format: str | None = None,
    ) -> tuple[str, int, int, int]:
        system = req.system or ""
        user = req.prompt

        if self._provider == "anthropic":
            kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": user}])
            if system:
                if cache_system:
                    ctrl: dict = {"type": "ephemeral"}
                    if cache_ttl == "1h":
                        ctrl["ttl"] = "1h"
                    kwargs["system"] = [{"type": "text", "text": system, "cache_control": ctrl}]
                else:
                    kwargs["system"] = system
            resp = self._raw.messages.create(**kwargs)
            usage = resp.usage
            cached = getattr(usage, "cache_read_input_tokens", 0) or 0
            return resp.content[0].text.strip(), usage.input_tokens, usage.output_tokens, cached

        if self._provider in ("openai", "ollama"):
            msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
            kwargs: dict[str, Any] = dict(model=model, max_tokens=max_tokens, messages=msgs)
            if response_format == "json":
                # OpenAI-compatible JSON mode. Requires the word "json" somewhere in the
                # prompt (OpenAI API constraint) — every response_format="json" caller's
                # prompt already asks for JSON output, since Anthropic has no native mode
                # and relies entirely on that instruction plus parse+repair fallback.
                kwargs["response_format"] = {"type": "json_object"}
            resp = self._raw.chat.completions.create(**kwargs)
            usage = resp.usage
            return resp.choices[0].message.content.strip(), usage.prompt_tokens, usage.completion_tokens, 0

        if self._provider == "google":
            from google.genai import types

            config: dict[str, Any] = {"max_output_tokens": max_tokens}
            if system:
                config["system_instruction"] = system
            if response_format == "json":
                config["response_mime_type"] = "application/json"
            config = types.GenerateContentConfig(**config)
            resp = self._raw.models.generate_content(model=model, contents=user, config=config)
            return (resp.text or "").strip(), 0, 0, 0

        raise RuntimeError(f"Unhandled provider: {self._provider}")


# ---------------------------------------------------------------------------
# Factory + top-level call()
# ---------------------------------------------------------------------------

_cache: dict[str, LLMClient] = {}
_lock = threading.Lock()


def get_client(role: str) -> LLMClient:
    """Return a cached LLMClient for the given pipeline role.

    Cached per role, not per provider: `rate_limits` is keyed by role (see
    docs/config.md), and two roles on the same provider can carry different
    requests_per_minute — sharing one client/throttle bucket across them would
    make one role's limit win for both, silently ignoring the other's config.
    """
    from job_hunter.config import get_config, get_secret
    from job_hunter.llm.providers import PROVIDER_SECRET_ENV_VARS, resolve_provider

    config = get_config("job_hunter")
    llm = config.get("llm", {})
    provider = resolve_provider(role, llm)

    with _lock:
        if role in _cache:
            return _cache[role]

        if provider == "ollama":
            api_key, base_url = "", llm.get("ollama", {}).get("base_url", "http://localhost:11434")
        else:
            env_var = PROVIDER_SECRET_ENV_VARS.get(provider, "")
            api_key = get_secret(env_var, required=bool(env_var)) if env_var else ""
            base_url = ""

        rpm = int(llm.get("rate_limits", {}).get(role, {}).get("requests_per_minute", 0) or 0)
        logger.info("[llm] initialising %s client for role '%s' (rpm=%d)", provider, role, rpm)
        client = LLMClient(provider, api_key=api_key, base_url=base_url, requests_per_minute=rpm)
        _cache[role] = client
        return client


def clear_cache() -> None:
    """Clear the provider client cache. For testing only."""
    with _lock:
        _cache.clear()


def call(role: str, prompt: str, system: str = "", cache_system: bool = False, cache_ttl: str = "5m") -> LLMResponse:
    """Convenience wrapper: resolve client + model + tokens from config, then call."""
    from job_hunter.llm.providers import resolve_model_config

    settings = resolve_model_config(role)
    req = LLMRequest(role=role, prompt=prompt, system=system or None)
    client = get_client(role)
    return client.complete(
        req,
        model=settings.model,
        max_tokens=settings.max_tokens,
        cache_system=cache_system,
        cache_ttl=cache_ttl,
    )
