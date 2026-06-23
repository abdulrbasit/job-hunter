"""Data ownership rules for safe product updates."""

from __future__ import annotations

from pathlib import Path

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


def unsafe_update_paths(
    paths: list[str | Path],
) -> list[str]:
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
