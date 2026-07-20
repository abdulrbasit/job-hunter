"""First-run desktop shortcut registration, opt-out.

Called from `job-hunter dash` on first run — click-icon-to-launch is the daily-use
goal; a terminal is only needed once. State (whether a shortcut was created, or the
user opted out) lives in launcher.platform_config_dir(), not the workspace — this is
OS app state, not a user choice about job search behavior, so it doesn't belong in
config/job_hunter.yml (see the OWNERSHIP PRINCIPLE in AGENTS.md).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_STATE_FILENAME = "app_state.json"
_DESKTOP_ENTRY = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=Job Hunter\n"
    "Comment=Autonomous job search assistant\n"
    "Exec={exe} dash\n"
    "Icon=job-hunter\n"
    "Terminal=false\n"
    "Categories=Office;Utility;\n"
)


def _state_path() -> Path:
    from job_hunter.launcher import platform_config_dir

    return platform_config_dir() / _STATE_FILENAME


def _read_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def record_opt_out() -> None:
    """`job-hunter dash --no-shortcut` calls this so future launches never create one."""
    state = _read_state()
    state["shortcut_optout"] = True
    _write_state(state)


def _create_windows_shortcut() -> bool:
    """Start Menu .lnk via WScript.Shell, run through PowerShell — no new dependency."""
    exe = shutil.which("job-hunter")
    if not exe:
        return False
    start_menu_base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    start_menu = Path(start_menu_base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    if not start_menu.is_dir():
        return False
    lnk_path = start_menu / "Job Hunter.lnk"
    script = (
        "$W = New-Object -ComObject WScript.Shell; "
        f'$S = $W.CreateShortcut("{lnk_path}"); '
        f'$S.TargetPath = "{exe}"; '
        '$S.Arguments = "dash"; '
        f'$S.WorkingDirectory = "{Path(exe).parent}"; '
        "$S.Save()"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def _create_linux_shortcut() -> bool:
    """~/.local/share/applications/job-hunter.desktop — mirrors packaging/linux/job-hunter.desktop."""
    exe = shutil.which("job-hunter") or "job-hunter"
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    (apps_dir / "job-hunter.desktop").write_text(_DESKTOP_ENTRY.format(exe=exe), encoding="utf-8")
    return True


def ensure_desktop_shortcut() -> None:
    """Create a desktop entry on first run, unless already created or opted out.

    macOS is skipped — a native .app install already puts Job Hunter in
    Applications/Launchpad; there's no separate shortcut to create for a
    `pip`/`uv tool install`. Never raises — a failed shortcut is a shrug, not a
    reason to block `dash` from opening.
    """
    state = _read_state()
    if state.get("shortcut_optout") or state.get("shortcut_created"):
        return
    try:
        if sys.platform == "win32":
            created = _create_windows_shortcut()
        elif sys.platform.startswith("linux"):
            created = _create_linux_shortcut()
        else:
            created = False
    except OSError:
        created = False
    if created:
        state["shortcut_created"] = True
        _write_state(state)
