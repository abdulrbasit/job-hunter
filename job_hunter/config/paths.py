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
    """Resolve a configured profile path relative to ROOT.

    Resume-related keys resolve through the base entry of profile.resumes when the
    map form is configured, so every existing caller keeps getting the base-language
    resume without knowing about multi-language config.

    An unset optional key with an empty default (e.g. profile_image) returns Path("")
    unjoined — never `ROOT / Path("")`, which collapses to ROOT itself (Path("") is
    ".") and would make an unconfigured optional asset look like an existing file/dir
    to callers checking `.exists()`. Path("").name is reliably empty either way, so
    callers can check `.name` to tell "unset" from "configured"."""
    from job_hunter.config.loader import get_job_hunter_config
    from job_hunter.config.resumes import SPEC_KEYS, base_resume_spec

    profile = get_job_hunter_config().get("profile", {})
    if key in SPEC_KEYS and isinstance(profile.get("resumes"), dict):
        value = base_resume_spec(profile).get(key) or default
    else:
        value = profile.get(key, default)
    if not value:
        return Path(value)
    path = Path(value)
    return path if path.is_absolute() else ROOT / path
