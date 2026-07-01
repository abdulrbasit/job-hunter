"""Provider and model routing: which provider/model/max_tokens a role uses."""

from __future__ import annotations

from job_hunter.llm.types import ModelConfig, ProviderName, RoleName

PROVIDER_SECRET_ENV_VARS: dict[ProviderName, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def resolve_provider(role: RoleName, llm_cfg: dict) -> ProviderName:
    """Return the configured provider for a role, falling back to the default provider."""
    provider = llm_cfg.get("providers", {}).get(role) or llm_cfg.get("default_provider", "anthropic")
    return provider


def resolve_model_config(role: RoleName, *, api_cfg: dict | None = None) -> ModelConfig:
    """Return provider, model, and max_tokens for a pipeline role from job_hunter.yml."""
    if api_cfg is None:
        from job_hunter.config.loader import get_config

        api_cfg = get_config("job_hunter")

    llm_cfg = api_cfg.get("llm", {})
    models = llm_cfg.get("models", {})
    if role not in models:
        raise KeyError(f"llm.models.{role}")
    max_tokens_cfg = llm_cfg.get("max_tokens", {})

    return ModelConfig(
        role=role,
        provider=resolve_provider(role, llm_cfg),
        model=models[role],
        max_tokens=int(max_tokens_cfg.get(role, 1000)),
    )
