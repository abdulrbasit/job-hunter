"""Detect which tool manages the installed job-hunter-kit package, for one-click upgrade."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

_PACKAGE = "job-hunter-kit"


@dataclass(frozen=True)
class Upgrader:
    tool: str
    command: list[str]


def _tool_manages_package(tool: str, list_args: list[str]) -> bool:
    if not shutil.which(tool):
        return False
    result = subprocess.run([tool, *list_args], capture_output=True, text=True, check=False)  # noqa: S603
    return result.returncode == 0 and _PACKAGE in result.stdout


def detect_upgrader() -> Upgrader | None:
    """Return the upgrade command for however job-hunter-kit was installed.

    None means undetectable — a PyInstaller-built binary (packaging/) has no bundled
    python/pip to upgrade in place; the caller should fall back to a copyable command
    or "download the latest installer" messaging.
    """
    if getattr(sys, "frozen", False):
        return None
    if _tool_manages_package("uv", ["tool", "list"]):
        return Upgrader("uv", ["uv", "tool", "upgrade", _PACKAGE])
    if _tool_manages_package("pipx", ["list"]):
        return Upgrader("pipx", ["pipx", "upgrade", _PACKAGE])
    return Upgrader("pip", [sys.executable, "-m", "pip", "install", "--upgrade", _PACKAGE])
