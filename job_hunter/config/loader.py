"""YAML config loading and merge.

Also re-exports ROOT, get_api_config, get_timeout, and get_mode so existing
`from job_hunter.config.loader import X` call sites across the codebase keep
working unchanged after the Phase 8 config split (paths.py, runtime.py,
secrets.py, removed_keys.py, schema.py). The runtime.* re-exports are lazy
(module __getattr__, PEP 562) to avoid a loader<->runtime import cycle —
runtime.py itself imports get_job_hunter_config from this module.
"""

from __future__ import annotations

import logging
from functools import cache
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import yaml

from job_hunter.config.defaults import (
    COVER_LETTER_DEFAULTS,
    LINKEDIN_DEFAULTS,
    LLM_ROLE_DEFAULTS,
    SCORING_PROMPT_CONTEXT,
    TAILORING_DEFAULTS,
    deep_merge,
)
from job_hunter.config.paths import ROOT, profile_path  # noqa: F401 (re-export)
from job_hunter.config.removed_keys import reject_removed_user_config


def _load_yaml(name: str) -> dict[str, Any]:
    path = ROOT / "config" / f"{name}.yml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _build_job_hunter_config(root: Path) -> dict[str, Any]:
    path = root / "config" / "job_hunter.yml"
    data: dict[str, Any] = {}
    if path.exists():
        with path.open(encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
    reject_removed_user_config(data)
    defaults: dict[str, Any] = {
        "llm": LLM_ROLE_DEFAULTS,
        "linkedin": LINKEDIN_DEFAULTS,
        "tailoring": TAILORING_DEFAULTS,
        "cover_letter": COVER_LETTER_DEFAULTS,
    }
    merged = deep_merge(defaults, data)
    from job_hunter.config.locations import canonicalize_config_regions

    merged = canonicalize_config_regions(merged, warn_legacy=True)
    scoring = merged.setdefault("scoring", {})
    scoring["prompt_context"] = SCORING_PROMPT_CONTEXT
    return merged


@cache
def get_job_hunter_config() -> dict[str, Any]:
    """Load config/job_hunter.yml and merge code-owned runtime defaults."""
    return _build_job_hunter_config(ROOT)


def get_job_hunter_config_for_root(root: Path) -> dict[str, Any]:
    """Same as get_job_hunter_config(), for an explicit non-default workspace root.

    ROOT is resolved once at import time from cwd/JOB_HUNTER_ROOT, so callers that
    operate on a different workspace root (multi-workspace tooling, tests) can't use
    the cached, ROOT-bound get_job_hunter_config() without silently loading the wrong
    workspace's config. Uncached — these callers are not a hot path.
    """
    return _build_job_hunter_config(root)


@cache
def get_config(name: str) -> dict[str, Any]:
    """Load canonical config by logical name."""
    if name == "job_hunter":
        return get_job_hunter_config()
    if name == "api_config":
        from job_hunter.config.runtime import get_api_config

        return get_api_config()
    return _load_yaml(name)


def package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("job-hunter-kit")
    except PackageNotFoundError:
        return "unknown"


def setup_logging(log_level: str = "INFO", log_file: str = "job_hunt.log") -> logging.Logger:
    """Configure root logger: console + rotating file handler."""
    log_path = ROOT / log_file

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers = []

    for lib in ("urllib3", "requests", "httpx", "httpcore", "anthropic", "openai", "charset_normalizer"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    console_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s")

    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(console_format)
    root.addHandler(console)

    file_handler = RotatingFileHandler(str(log_path), maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_format)
    root.addHandler(file_handler)

    return logging.getLogger("job_hunter")


_LAZY_RUNTIME_REEXPORTS = frozenset({"get_api_config", "get_timeout", "get_mode"})


def __getattr__(name: str):
    if name in _LAZY_RUNTIME_REEXPORTS:
        import job_hunter.config.runtime as _runtime

        return getattr(_runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
