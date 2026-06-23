"""Shim: maps legacy core config names to local job_hunter.config.loader equivalents."""

from __future__ import annotations

from job_hunter.config.defaults import SECRET_ENV_VARS
from job_hunter.config.loader import (
    ROOT,
    get_api_config,
    get_config,
    get_mode,
    get_secret,
    get_timeout,
    profile_path,
    setup_logging,
)

# Backward-compat alias: job-hunter-core used load_api_config, local uses get_api_config
load_api_config = get_api_config

__all__ = [
    "ROOT",
    "get_api_config",
    "get_config",
    "get_mode",
    "get_secret",
    "get_timeout",
    "load_api_config",
    "profile_path",
    "setup_logging",
    # API key constants below
    "RAPIDAPI_KEY",
    "ADZUNA_API_KEY",
    "ADZUNA_APP_ID",
    "JOOBLE_API_KEY",
    "REED_API_KEY",
    "FIRECRAWL_API_KEY",
    "BRAVE_API_KEY",
    "EXA_API_KEY",
    "TAVILY_API_KEY",
    "package_version",
]


def _env(name: str) -> str:
    """Read an API key from its fixed environment variable name."""
    return get_secret(name, required=False)


RAPIDAPI_KEY: str = _env(SECRET_ENV_VARS["rapidapi"])
ADZUNA_API_KEY: str = _env(SECRET_ENV_VARS["adzuna_api_key"])
ADZUNA_APP_ID: str = _env(SECRET_ENV_VARS["adzuna_app_id"])
JOOBLE_API_KEY: str = _env(SECRET_ENV_VARS["jooble"])
REED_API_KEY: str = _env(SECRET_ENV_VARS["reed"])
FIRECRAWL_API_KEY: str = _env(SECRET_ENV_VARS["firecrawl"])
BRAVE_API_KEY: str = _env(SECRET_ENV_VARS["brave"])
EXA_API_KEY: str = _env(SECRET_ENV_VARS["exa"])
TAVILY_API_KEY: str = _env(SECRET_ENV_VARS["tavily"])


def package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("job-hunter-kit")
    except PackageNotFoundError:
        return "unknown"
