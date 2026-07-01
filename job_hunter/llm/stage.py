from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from job_hunter.core.llm_utils import extract_json_object
from job_hunter.llm.client import get_client as get_llm_client
from job_hunter.llm.providers import resolve_model_config
from job_hunter.llm.token_usage import record_tokens
from job_hunter.llm.types import LLMRequest, TokenUsage


@dataclass
class LLMStage:
    role: str
    response_format: str | None = None
    cache_system: bool = False
    cache_ttl: str | None = None
    client_factory: Callable[[str], Any] = get_llm_client
    settings_factory: Callable[..., Any] = resolve_model_config

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
        usage = TokenUsage(
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cached_tokens=response.cached_tokens,
        )
        record_tokens(self.role, usage)
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
