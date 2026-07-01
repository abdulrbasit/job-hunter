"""Workspace root and path resolution."""

from __future__ import annotations

import os
from pathlib import Path


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


def profile_path(key: str, default: str) -> Path:
    """Resolve a configured profile path relative to ROOT."""
    from job_hunter.config.loader import get_job_hunter_config

    profile = get_job_hunter_config().get("profile", {})
    value = profile.get(key, default)
    path = Path(value)
    return path if path.is_absolute() else ROOT / path
