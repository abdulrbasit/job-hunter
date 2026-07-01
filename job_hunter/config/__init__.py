"""Config package — YAML loading, secret resolution, logging, root detection.

Usage:
    from job_hunter.config import get_config, get_secret, get_mode, ROOT
"""

from job_hunter.config.loader import (
    get_config,
    get_job_hunter_config,
    package_version,
    setup_logging,
)
from job_hunter.config.paths import ROOT, profile_path
from job_hunter.config.removed_keys import reject_removed_user_config
from job_hunter.config.runtime import get_api_config, get_mode, get_timeout
from job_hunter.config.secrets import get_secret

__all__ = [
    "ROOT",
    "ADZUNA_API_KEY",
    "ADZUNA_APP_ID",
    "BRAVE_API_KEY",
    "EXA_API_KEY",
    "FIRECRAWL_API_KEY",
    "JOOBLE_API_KEY",
    "RAPIDAPI_KEY",
    "REED_API_KEY",
    "TAVILY_API_KEY",
    "get_api_config",
    "get_config",
    "get_job_hunter_config",
    "get_mode",
    "get_secret",
    "get_timeout",
    "package_version",
    "profile_path",
    "reject_removed_user_config",
    "setup_logging",
]

_LAZY_SECRET_NAMES = frozenset(
    {
        "ADZUNA_API_KEY",
        "ADZUNA_APP_ID",
        "BRAVE_API_KEY",
        "EXA_API_KEY",
        "FIRECRAWL_API_KEY",
        "JOOBLE_API_KEY",
        "RAPIDAPI_KEY",
        "REED_API_KEY",
        "TAVILY_API_KEY",
    }
)


def __getattr__(name: str) -> str:
    if name in _LAZY_SECRET_NAMES:
        import job_hunter.config.secrets as _secrets

        return getattr(_secrets, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
