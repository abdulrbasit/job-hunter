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

Call via call(role, prompt, system) — never instantiate LLMClient directly.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from job_hunter.models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


def _compress_request(prompt: str, system: str, model: str) -> tuple[str, str]:
    """Compress prompt and system context via headroom before sending to the LLM."""
    try:
        from headroom import compress  # noqa: PLC0415

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        compressed = compress(messages, model=model)
        c_system = next((m["content"] for m in compressed if m.get("role") == "system"), system)
        c_prompt = next((m["content"] for m in compressed if m.get("role") == "user"), prompt)
        return c_prompt, c_system
    except Exception:
        return prompt, system


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
                raise ImportError("pip install anthropic") from None
            return Anthropic(api_key=api_key)

        if provider == "openai":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("pip install openai") from None
            return OpenAI(api_key=api_key)

        if provider == "google":
            try:
                from google import genai
            except ImportError:
                raise ImportError("pip install google-genai") from None
            return genai.Client(api_key=api_key)

        if provider == "ollama":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("pip install openai  # Ollama uses OpenAI-compatible API") from None
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
            resp = self._raw.chat.completions.create(model=model, max_tokens=max_tokens, messages=msgs)
            usage = resp.usage
            return resp.choices[0].message.content.strip(), usage.prompt_tokens, usage.completion_tokens, 0

        if self._provider == "google":
            cfg_kwargs = google_generation_config_kwargs(system, max_tokens, response_format)
            from google.genai import types

            config = types.GenerateContentConfig(**cfg_kwargs)
            resp = self._raw.models.generate_content(model=model, contents=user, config=config)
            return (resp.text or "").strip(), 0, 0, 0

        raise RuntimeError(f"Unhandled provider: {self._provider}")


# ---------------------------------------------------------------------------
# Factory + top-level call()
# ---------------------------------------------------------------------------

_cache: dict[str, LLMClient] = {}
_lock = threading.Lock()


def get_client(role: str) -> LLMClient:
    """Return a cached LLMClient for the given pipeline role."""
    from job_hunter.config import get_config, get_secret
    from job_hunter.config.defaults import PROVIDER_SECRET_ENV_VARS

    cfg = get_config("job_hunter")
    llm = cfg.get("llm", {})
    provider: str = llm.get("providers", {}).get(role) or llm.get("default_provider", "anthropic")

    with _lock:
        if provider in _cache:
            return _cache[provider]

        if provider == "ollama":
            api_key, base_url = "", llm.get("ollama", {}).get("base_url", "http://localhost:11434")
        else:
            env_var = PROVIDER_SECRET_ENV_VARS.get(provider, "")
            api_key = get_secret(env_var, required=bool(env_var)) if env_var else ""
            base_url = ""

        rpm = int(llm.get("rate_limits", {}).get(provider, {}).get("requests_per_minute", 0) or 0)
        logger.info("[llm] initialising %s client for role '%s'", provider, role)
        client = LLMClient(provider, api_key=api_key, base_url=base_url, requests_per_minute=rpm)
        _cache[provider] = client
        return client


def call(role: str, prompt: str, system: str = "", cache_system: bool = False, cache_ttl: str = "5m") -> LLMResponse:
    """Convenience wrapper: resolve client + model + tokens from config, then call."""
    from job_hunter.core.llm_utils import get_llm_role_settings

    settings = get_llm_role_settings(role)
    req = LLMRequest(role=role, prompt=prompt, system=system or None)
    client = get_client(role)
    return client.complete(
        req,
        model=settings.model,
        max_tokens=settings.max_tokens,
        cache_system=cache_system,
        cache_ttl=cache_ttl,
    )


def google_generation_config_kwargs(
    system: str | None,
    max_tokens: int,
    response_format: str | None = None,
) -> dict[str, Any]:
    """Build kwargs for Google GenerateContentConfig without importing the SDK."""
    kwargs: dict[str, Any] = {"max_output_tokens": max_tokens}
    if system:
        kwargs["system_instruction"] = system
    if response_format == "json":
        kwargs["response_mime_type"] = "application/json"
    return kwargs
