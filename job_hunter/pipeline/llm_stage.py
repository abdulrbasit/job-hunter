from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from job_hunter.core.llm_utils import extract_json_object, get_llm_role_settings
from job_hunter.llm.client import get_client as get_llm_client

_token_totals: dict[str, dict[str, int]] = {}
_token_lock = threading.Lock()


def _record_tokens(role: str, in_tok: int, out_tok: int, cached: int) -> None:
    with _token_lock:
        b = _token_totals.setdefault(role, {"in": 0, "out": 0, "cached": 0})
        b["in"] += in_tok
        b["out"] += out_tok
        b["cached"] += cached


def get_token_totals() -> dict[str, dict[str, int]]:
    with _token_lock:
        return {k: dict(v) for k, v in _token_totals.items()}


def reset_token_totals() -> None:
    with _token_lock:
        _token_totals.clear()


@dataclass
class LLMStage:
    role: str
    response_format: str | None = None
    cache_system: bool = False
    cache_ttl: str | None = None
    client_factory: Callable[[str], Any] = get_llm_client
    settings_factory: Callable[..., Any] = get_llm_role_settings

    def settings(self, api_cfg: dict | None = None) -> Any:
        if api_cfg is None:
            return self.settings_factory(self.role)
        return self.settings_factory(self.role, api_cfg=api_cfg)

    def complete(
        self,
        *,
        system: str,
        user: str,
        api_cfg: dict | None = None,
        response_format: str | None = None,
        cache_system: bool | None = None,
        cache_ttl: str | None = None,
    ) -> str:
        from job_hunter.models import LLMRequest

        settings = self.settings(api_cfg)
        resolved_format = self.response_format if response_format is None else response_format
        resolved_cache = self.cache_system if cache_system is None else cache_system
        resolved_ttl = self.cache_ttl if cache_ttl is None else cache_ttl
        req = LLMRequest(role=self.role, prompt=user, system=system or None)
        response = self.client_factory(self.role).complete(
            req,
            model=settings.model,
            max_tokens=settings.max_tokens,
            cache_system=resolved_cache,
            cache_ttl=resolved_ttl or "5m",
            response_format=resolved_format,
        )
        _record_tokens(self.role, response.input_tokens, response.output_tokens, response.cached_tokens)
        return response.content

    @staticmethod
    def parse_json_object(raw: str, error_message: str) -> dict:
        result = json.loads(extract_json_object(raw))
        if not isinstance(result, dict):
            raise ValueError(error_message)
        return result

    def repair_json_object(
        self,
        *,
        system: str,
        raw: str,
        repair_prompt: str,
        max_chars: int,
        error_message: str,
        api_cfg: dict | None = None,
    ) -> dict:
        repaired = self.complete(
            system=system,
            user=repair_prompt.format(raw=raw[:max_chars]),
            api_cfg=api_cfg,
        )
        return self.parse_json_object(repaired, error_message)
