"""Runs out-of-process, spawned detached by ux/web/api.py::DashAPI.start_self_update right
before the dashboard window closes: upgrades the installed package, refreshes workspace
assets, and relaunches the dashboard. See start_self_update's docstring for why this can't
happen in-process (Windows locks the running executable; every OS keeps old code loaded
in memory).

No explicit wait for the old process's pid to exit — cross-platform pid-liveness checks
need OS-specific code (ctypes on Windows) for no real benefit here. What actually matters
is whether the installed console-script is still locked by the exiting process; a short
grace period plus retrying the upgrade command on failure observes that directly instead
of inferring it from process state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from job_hunter.update.upgrader import Upgrader

_GRACE_PERIOD_SECONDS = 2.0
_UPGRADE_ATTEMPTS = 4
_UPGRADE_RETRY_DELAY_SECONDS = 2.0
_LAST_RESULT_FILENAME = "last_update.json"


def _last_result_path() -> Path:
    from job_hunter.launcher import platform_config_dir

    return platform_config_dir() / _LAST_RESULT_FILENAME


def read_last_result() -> dict[str, Any] | None:
    """The previous self-update's outcome, for a post-restart toast. None if there isn't one."""
    path = _last_result_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def clear_last_result() -> None:
    path = _last_result_path()
    if path.exists():
        path.unlink()


def _write_result(result: dict[str, Any]) -> None:
    path = _last_result_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result), encoding="utf-8")


def _run_upgrade(upgrader: Upgrader) -> tuple[bool, str]:
    last_error = ""
    for attempt in range(_UPGRADE_ATTEMPTS):
        if attempt:
            time.sleep(_UPGRADE_RETRY_DELAY_SECONDS)
        proc = subprocess.run(upgrader.command, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return True, proc.stdout.strip()
        last_error = proc.stderr.strip() or proc.stdout.strip()
    return False, last_error


def detached_popen_kwargs(cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    """subprocess.Popen kwargs to spawn a process that outlives its parent, on any OS.

    Shared by self-update's own relaunch below and by DashAPI.start_self_update, which
    spawns this module's CLI entry point (`job-hunter internal self-update`) the same way.
    """
    kwargs: dict[str, Any] = {"cwd": str(cwd), "env": env if env is not None else os.environ}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _relaunch_dashboard(workspace: Path) -> None:
    env = {**os.environ, "JOB_HUNTER_ROOT": str(workspace)}
    subprocess.Popen(["job-hunter", "dash"], **detached_popen_kwargs(workspace, env))


def run_self_update(workspace: Path, upgrader: Upgrader, *, from_version: str) -> dict[str, Any]:
    """Upgrade the installed package, refresh workspace assets, relaunch the dashboard.

    Meant to be invoked as `job-hunter internal self-update` — see
    cli/commands/update.py::self_update_cmd and DashAPI.start_self_update.
    """
    time.sleep(_GRACE_PERIOD_SECONDS)

    ok, message = _run_upgrade(upgrader)
    if not ok:
        result = {
            "ok": False,
            "stage": "upgrade",
            "from": from_version,
            "message": message or "Package upgrade failed.",
            "fallback_command": " ".join(upgrader.command),
        }
        _write_result(result)
        return result

    workspace_proc = subprocess.run(
        ["job-hunter", "update", "--yes", "--workspace", str(workspace)],
        capture_output=True,
        text=True,
        check=False,
    )
    if workspace_proc.returncode != 0:
        result = {
            "ok": False,
            "stage": "workspace_update",
            "from": from_version,
            "message": workspace_proc.stderr.strip() or "Package upgraded, but the workspace update failed.",
            "fallback_command": "job-hunter update --yes",
        }
        _write_result(result)
        return result

    from job_hunter.update.versions import installed_version

    result = {"ok": True, "stage": "done", "from": from_version, "to": installed_version()}
    _write_result(result)
    _relaunch_dashboard(workspace)
    return result
