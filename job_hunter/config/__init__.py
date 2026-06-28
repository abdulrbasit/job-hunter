"""Config package — YAML loading, secret resolution, logging, root detection.

Usage:
    from job_hunter.config import get_config, get_secret, get_mode, ROOT
"""

from job_hunter.config.loader import (
    ADZUNA_API_KEY,
    ADZUNA_APP_ID,
    BRAVE_API_KEY,
    EXA_API_KEY,
    FIRECRAWL_API_KEY,
    JOOBLE_API_KEY,
    RAPIDAPI_KEY,
    REED_API_KEY,
    ROOT,
    TAVILY_API_KEY,
    get_api_config,
    get_config,
    get_mode,
    get_secret,
    get_timeout,
    package_version,
    profile_path,
    setup_logging,
)

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
    "get_mode",
    "get_secret",
    "get_timeout",
    "package_version",
    "profile_path",
    "setup_logging",
]
