"""Desktop launcher: recent-workspace resolution and workspace create/open.

Runs before any root-bound product module is imported — callers must set
JOB_HUNTER_ROOT from the result of resolve_launch_root()/create_workspace()/
open_workspace() before importing job_hunter.config.loader or anything that
depends on it (ROOT is resolved once at import time; see config/paths.py).
Switching workspaces means restarting the process with a new JOB_HUNTER_ROOT,
not a live in-process switch.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from job_hunter.workspace.manifest import MANIFEST_PATH
from job_hunter.workspace.operations import InitResult, run_init

_RECENT_WORKSPACE_FILENAME = "recent_workspace.json"


def platform_config_dir() -> Path:
    """Platform-native per-user config directory for job-hunter's own app state.

    Not a workspace path — this stores which workspace to open on next launch.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "job-hunter"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "job-hunter"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "job-hunter"


def is_valid_workspace(path: Path) -> bool:
    return (path / MANIFEST_PATH).exists() or (path / "config" / "job_hunter.yml").exists()


def get_recent_workspace() -> Path | None:
    """Return the last-opened workspace path, or None if unset/invalid/gone."""
    recent_path = platform_config_dir() / _RECENT_WORKSPACE_FILENAME
    if not recent_path.exists():
        return None
    try:
        data = json.loads(recent_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    raw = data.get("workspace")
    if not raw:
        return None
    candidate = Path(raw)
    return candidate if candidate.is_dir() and is_valid_workspace(candidate) else None


def set_recent_workspace(path: Path) -> None:
    config_dir = platform_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    recent_path = config_dir / _RECENT_WORKSPACE_FILENAME
    recent_path.write_text(json.dumps({"workspace": str(path.resolve())}), encoding="utf-8")


def resolve_launch_root() -> Path | None:
    """The workspace to open automatically, or None to show Create/Open Workspace."""
    return get_recent_workspace()


def create_workspace(path: Path, *, force: bool = False) -> InitResult:
    """Create a new workspace at path and remember it as the recent workspace."""
    result = run_init(path, force=force)
    set_recent_workspace(result.workspace)
    return result


def open_workspace(path: Path) -> Path:
    """Open an existing workspace at path and remember it as the recent workspace.

    Raises FileNotFoundError if path is not a valid job-hunter workspace.
    """
    resolved = path.resolve()
    if not is_valid_workspace(resolved):
        raise FileNotFoundError(f"{resolved} is not a job-hunter workspace (no manifest or config found)")
    set_recent_workspace(resolved)
    return resolved


def bootstrap_launch_state() -> dict[str, Any]:
    """What the launcher UI needs before any workspace root is known: recent workspace or none."""
    recent = resolve_launch_root()
    return {"recent_workspace": str(recent) if recent else None}
