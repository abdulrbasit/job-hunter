"""Snapshot/rollback for system-owned workspace files before an update overwrites them.

Only the single most-recent snapshot is kept — one-click rollback undoes the last
update, not arbitrary history. outputs/ is already user-owned/regenerable per
DATA_CONTRACT.md, so storing the snapshot there needs no new ownership carve-out.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from job_hunter.workspace.assets import UPDATE_ASSETS
from job_hunter.workspace.safety import classify_path

_SNAPSHOT_DIR_PARTS = ("outputs", "state", "update_snapshot")
# Deliberately not workspace.safety.SYSTEM_LAYER_PREFIXES — that list also includes
# job_hunter/, tests/, docs/ for the dev-repo checkout case, which would make a snapshot
# walk the entire package source tree if the workspace root happens to be the repo itself.
_MANAGED_DIRS = (".claude/skills", ".agents/skills", ".github")


def _snapshot_root(workspace: Path) -> Path:
    return workspace.joinpath(*_SNAPSHOT_DIR_PARTS)


def _iter_snapshot_targets(workspace: Path) -> list[Path]:
    """Every file update_workspace_assets()/update_skills()/update_workflows() may overwrite."""
    targets = [workspace / rel for rel in UPDATE_ASSETS]
    for rel_dir in _MANAGED_DIRS:
        base = workspace / rel_dir
        if base.is_dir():
            targets.extend(p for p in base.rglob("*") if p.is_file())
    return [t for t in targets if t.is_file() and classify_path(t.relative_to(workspace)) == "system"]


def snapshot_system_files(workspace: Path) -> int:
    """Copy current system-owned files into the snapshot dir, replacing any prior snapshot."""
    workspace = workspace.resolve()
    root = _snapshot_root(workspace)
    if root.exists():
        shutil.rmtree(root)
    count = 0
    for src in _iter_snapshot_targets(workspace):
        dest = root / src.relative_to(workspace)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        count += 1
    return count


def rollback_last(workspace: Path) -> int:
    """Restore the most recent snapshot over the workspace. Returns files restored, 0 if none exists."""
    workspace = workspace.resolve()
    root = _snapshot_root(workspace)
    if not root.is_dir():
        return 0
    count = 0
    for src in root.rglob("*"):
        if not src.is_file():
            continue
        dest = workspace / src.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        count += 1
    return count
