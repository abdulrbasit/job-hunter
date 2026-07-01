"""LLM contracts: request/response, token accounting, provider/model routing types.

Every LLM call in this codebase crosses these types. No module should invent
its own ad hoc shape for an LLM request, response, or model selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

RoleName = Literal[
    "validation",
    "scoring",
    "tailoring",
    "cover_letter",
    "research",
    "linkedin",
    "jd_extraction",
]

ProviderName = Literal["anthropic", "openai", "google", "ollama"]


class LLMRequest(BaseModel):
    """Input to the LLM client."""

    role: RoleName
    prompt: str
    system: str | None = None
    max_tokens: int | None = None


class LLMResponse(BaseModel):
    """Output from the LLM client."""

    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


@dataclass(frozen=True)
class ModelConfig:
    """Resolved provider/model/max_tokens for a pipeline role."""

    role: RoleName
    provider: ProviderName
    model: str
    max_tokens: int
