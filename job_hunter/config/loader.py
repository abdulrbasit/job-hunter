"""YAML config loading, fixed secret resolution, root detection, and logging setup."""

from __future__ import annotations

import logging
import os
from functools import cache
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from job_hunter.config.defaults import (
    COVER_LETTER_DEFAULTS,
    HTTP_DEFAULTS,
    LINKEDIN_DEFAULTS,
    LLM_ROLE_DEFAULTS,
    SCORING_PROMPT_CONTEXT,
    TAILORING_DEFAULTS,
    deep_merge,
)


def _resolve_root() -> Path:
    """Find the user workspace root."""
    env_root = os.environ.get("JOB_HUNTER_ROOT")
    if env_root:
        path = Path(env_root).resolve()
        if path.exists():
            return path

    cwd = Path.cwd().resolve()
    for path in [cwd, *cwd.parents]:
        if (path / ".job-hunter" / "manifest.json").exists():
            return path
        if (path / "config" / "job_hunter.yml").exists():
            return path

    package_root = Path(__file__).resolve().parents[2]
    if (package_root / "config" / "job_hunter.yml").exists():
        return package_root

    return cwd


ROOT: Path = _resolve_root()


def _load_yaml(name: str) -> dict[str, Any]:
    path = ROOT / "config" / f"{name}.yml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


@cache
def get_job_hunter_config() -> dict[str, Any]:
    """Load config/job_hunter.yml and merge code-owned runtime defaults."""
    data = _load_yaml("job_hunter")
    _reject_removed_user_config(data)
    defaults: dict[str, Any] = {
        "llm": LLM_ROLE_DEFAULTS,
        "linkedin": LINKEDIN_DEFAULTS,
        "tailoring": TAILORING_DEFAULTS,
        "cover_letter": COVER_LETTER_DEFAULTS,
    }
    merged = deep_merge(defaults, data)
    scoring = merged.setdefault("scoring", {})
    scoring["prompt_context"] = SCORING_PROMPT_CONTEXT
    return merged


def _reject_removed_user_config(data: dict[str, Any]) -> None:
    """Fail fast when a workspace still uses pre-cutoff config keys."""
    found = [key for key in ("about_me", "sources", "secrets", "tailoring", "cover_letter") if key in data]

    exclusions = data.get("exclusions", {}) or {}
    for key in ("senior_flags", "stale_indicators", "url_patterns", "language_indicators"):
        if key in exclusions:
            found.append(f"exclusions.{key}")

    scoring = data.get("scoring", {}) or {}
    if "prompt_context" in scoring:
        found.append("scoring.prompt_context")

    linkedin = data.get("linkedin", {}) or {}
    rich_linkedin_keys = sorted(set(linkedin) - {"enabled"})
    found.extend(f"linkedin.{key}" for key in rich_linkedin_keys)

    if found:
        joined = ", ".join(found)
        raise ValueError(f"Removed job_hunter.yml key(s): {joined}. Update to the v1 compact config shape.")


@cache
def get_api_config() -> dict[str, Any]:
    """Return code-owned API/runtime settings with user LLM settings merged in."""
    cfg = get_job_hunter_config()
    llm = cfg.get("llm", {}) or {}
    return {
        "llm": {
            "provider": llm.get("default_provider", "anthropic"),
            "default_provider": llm.get("default_provider", "anthropic"),
            "providers": llm.get("providers", {}) or {},
            "models": llm.get("models", {}) or {},
            "max_tokens": llm.get("max_tokens", {}) or {},
            "max_workers": int(llm.get("max_workers", 5) or 5),
            "rate_limits": llm.get("rate_limits", {}) or {},
            "ollama": llm.get("ollama", {}) or {},
        },
        "http": HTTP_DEFAULTS,
        "profile": cfg.get("profile", {}) or {},
    }


@cache
def get_config(name: str) -> dict[str, Any]:
    """Load canonical config by logical name."""
    if name == "job_hunter":
        return get_job_hunter_config()
    if name == "api_config":
        return get_api_config()
    return _load_yaml(name)


def get_mode() -> Literal["agent", "llm-api"]:
    """Return the execution mode from config/job_hunter.yml."""
    raw = get_job_hunter_config().get("mode", "agent")
    if raw not in ("agent", "llm-api"):
        raise ValueError(f"Invalid mode '{raw}' in job_hunter.yml; must be agent or llm-api")
    return cast(Literal["agent", "llm-api"], raw)


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


_TIMEOUT_DEFAULTS: dict[str, int] = {
    "ats_scraper": 10,
    "playwright": 10,
    "lightpanda": 8,
    "firecrawl": 20,
    "job_boards": 15,
    "search_providers": 10,
    "jd_fetcher": 10,
}


def get_timeout(section: str) -> int:
    """Return timeout_seconds for a given HTTP section from code defaults."""
    configured = get_api_config().get("http", {}).get(section, {}).get("timeout_seconds")
    if configured is not None:
        return int(configured)
    if section in _TIMEOUT_DEFAULTS:
        return _TIMEOUT_DEFAULTS[section]
    raise KeyError(f"No timeout default for section: {section}")


def profile_path(key: str, default: str) -> Path:
    """Resolve a configured profile path relative to ROOT."""
    profile = get_job_hunter_config().get("profile", {})
    value = profile.get(key, default)
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


load_api_config = get_api_config


def package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("job-hunter-kit")
    except PackageNotFoundError:
        return "unknown"


def _env(name: str) -> str:
    from job_hunter.config.defaults import SECRET_ENV_VARS

    return get_secret(SECRET_ENV_VARS[name], required=False)


RAPIDAPI_KEY: str = _env("rapidapi")
ADZUNA_API_KEY: str = _env("adzuna_api_key")
ADZUNA_APP_ID: str = _env("adzuna_app_id")
JOOBLE_API_KEY: str = _env("jooble")
REED_API_KEY: str = _env("reed")
FIRECRAWL_API_KEY: str = _env("firecrawl")
BRAVE_API_KEY: str = _env("brave")
EXA_API_KEY: str = _env("exa")
TAVILY_API_KEY: str = _env("tavily")


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
