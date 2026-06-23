"""Helpers for enforcing safe system updates."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from job_hunter.data_contract import changed_paths_from_status, classify_path, unsafe_update_paths


def classify_paths(paths: list[str]) -> list[dict[str, str]]:
    return [{"path": path, "layer": classify_path(path)} for path in paths]


def update_safety_report(
    root: Path,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    """Return a report showing whether changed paths are safe for auto-update."""
    checked_paths = paths if paths is not None else _git_changed_paths(root)
    unsafe = unsafe_update_paths(checked_paths)
    return {
        "ok": not unsafe,
        "paths": classify_paths(checked_paths),
        "unsafe": unsafe,
    }


def _git_changed_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],  # noqa: S607
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    return changed_paths_from_status(result.stdout)
