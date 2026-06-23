"""Config package — YAML loading, secret resolution, logging, root detection.

Usage:
    from job_hunter.config import get_config, get_secret, get_mode, ROOT
"""

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

__all__ = [
    "ROOT",
    "get_api_config",
    "get_config",
    "get_mode",
    "get_secret",
    "get_timeout",
    "profile_path",
    "setup_logging",
]
