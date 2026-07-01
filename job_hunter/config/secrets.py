"""Env/keyring secret resolution.

The fixed API-key constants below (ADZUNA_API_KEY, etc.) resolve lazily on first
access via module __getattr__ (PEP 562), not at import time — importing this
module, or anything that imports it, no longer triggers env var lookups or a
keyring subprocess call as a side effect.
"""

from __future__ import annotations

import os
from functools import cache

from job_hunter.config.defaults import SECRET_ENV_VARS


def get_secret(env_var: str | None, *, required: bool = True) -> str:
    """Resolve a secret by env-var name. Checks os.environ then keyring."""
    if not env_var:
        if required:
            raise RuntimeError("No env_var name provided for this secret.")
        return ""

    value = os.environ.get(env_var)
    if value:
        return value

    try:
        import keyring

        value = keyring.get_password("job-hunter", env_var)
        if value:
            return value
    except Exception as exc:
        if not required:
            return ""
        raise RuntimeError(f"keyring unavailable: {exc}. Install with: pip install 'job-hunter-kit[secrets]'") from exc

    if not required:
        return ""
    raise RuntimeError(
        f"Secret '{env_var}' not found.\n"
        f"  Local: python -c \"import keyring; keyring.set_password('job-hunter', '{env_var}', 'YOUR_VALUE')\"\n"
        f"  GitHub Actions: add '{env_var}' to repo Secrets and reference it in the workflow env: block."
    )


_LAZY_SECRET_KEYS: dict[str, str] = {
    "RAPIDAPI_KEY": "rapidapi",
    "ADZUNA_API_KEY": "adzuna_api_key",
    "ADZUNA_APP_ID": "adzuna_app_id",
    "JOOBLE_API_KEY": "jooble",
    "REED_API_KEY": "reed",
    "FIRECRAWL_API_KEY": "firecrawl",
    "BRAVE_API_KEY": "brave",
    "EXA_API_KEY": "exa",
    "TAVILY_API_KEY": "tavily",
}


@cache
def _resolve_lazy_secret(name: str) -> str:
    return get_secret(SECRET_ENV_VARS[_LAZY_SECRET_KEYS[name]], required=False)


def __getattr__(name: str) -> str:
    if name in _LAZY_SECRET_KEYS:
        return _resolve_lazy_secret(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
