"""Data ownership rules and update-safety checks for automated workspace updates.

Merged from data_contract.py + update_safety.py (Phase 8) — the two were always
used together (classify -> report -> gate) and nothing outside workspace/+cli/
imported either separately.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

USER_LAYER_PREFIXES = (
    "config/",
    "profile/",
    "outputs/",
    "writing-samples/",
)
USER_LAYER_EXACT = (
    ".env",
    "DATA_LOCAL.md",
)
SYSTEM_LAYER_PREFIXES = (
    ".claude/skills/",
    ".github/ISSUE_TEMPLATE/",
    ".github/scripts/",
    ".github/workflows/",
    "config/schemas/",
    "docs/",
    "job_hunter/",
    "tests/",
)
SYSTEM_LAYER_EXACT = (
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "DATA_CONTRACT.md",
    "GEMINI.md",
    "LICENSE",
    "README.md",
    "SETUP.md",
    "pyproject.toml",
)


def normalize_repo_path(path: str | Path) -> str:
    """Return a stable slash-separated relative path."""
    text = str(path).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/") if text != "." else ""


def classify_path(path: str | Path) -> str:
    """Classify a repo path as user, system, or unknown."""
    rel = normalize_repo_path(path)
    if not rel:
        return "unknown"
    rel_dir = rel + "/"
    if rel in USER_LAYER_EXACT:
        return "user"
    if rel in SYSTEM_LAYER_EXACT:
        return "system"
    if any(rel.startswith(prefix) or rel_dir == prefix for prefix in SYSTEM_LAYER_PREFIXES):
        return "system"
    if any(rel.startswith(prefix) or rel_dir == prefix for prefix in USER_LAYER_PREFIXES):
        return "user"
    return "unknown"


def unsafe_update_paths(paths: list[str | Path]) -> list[str]:
    """Return paths that an automated product update must not modify."""
    unsafe: list[str] = []
    for path in paths:
        rel = normalize_repo_path(path)
        if classify_path(rel) != "system":
            unsafe.append(rel)
    return unsafe


def changed_paths_from_status(status: str) -> list[str]:
    """Parse `git status --porcelain` output into changed file paths."""
    paths: list[str] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        # Porcelain v1 uses two status columns, a space, then the path. Rename
        # entries include "old -> new"; the new path is the one updates would write.
        path = line[3:].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        paths.append(normalize_repo_path(path))
    return paths


def classify_paths(paths: list[str]) -> list[dict[str, str]]:
    return [{"path": path, "layer": classify_path(path)} for path in paths]


def dirty_system_paths(root: Path) -> list[str]:
    """Return currently git-dirty paths that fall in the system layer (skills, workflows,
    schemas, etc.) — the files an automated `job-hunter update` is about to overwrite.

    Used to warn the user before local edits to those files are silently discarded by an
    update, instead of failing open. Raises RuntimeError if `root` isn't a git repo or git
    isn't available — callers should treat that as "nothing to compare against", not an error.
    """
    changed = _git_changed_paths(root)
    return [path for path in changed if classify_path(path) == "system"]


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
