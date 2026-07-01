"""Temporary one-release bridge migration for pre-refactor workspaces.

Only two workspaces need this: Abdul's and one friend's, both created with
package versions before the Phase 8-13 refactor. Files below were deleted or
renamed during that refactor but the regular update flow never removes them
(only `.claude/skills/` staleness is tracked in the manifest today), so they
would linger in old workspaces forever without this bridge.

Remove after Abdul and the friend have both upgraded and run `job-hunter
update` successfully once with BRIDGE_MIGRATION_ID recorded in their
manifest. Cleanup checklist for that release:
  - delete this file
  - delete tests/test_bridge_migration.py
  - remove the bridge_migration import/call and --dry-run plumbing tied to
    it in job_hunter/cli/commands/update.py (keep --dry-run itself only if
    another use for it has shown up by then)
  - remove `applied_migrations` handling in update.py if nothing else uses it
  - keep manifest.py's `applied_migrations` field and normal update/skills/
    workflows behavior — those are permanent, not part of this bridge
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import typer

from job_hunter.workspace.manifest import is_protected, sha256_file

BRIDGE_MIGRATION_ID = "refactor-bridge-2026-07"

# rel path -> sha256 hashes of every content variant ever shipped for that
# path. Deleted only when the workspace copy matches one of these exactly
# (i.e. never edited by the user); anything else is preserved with a warning.
_OBSOLETE_FILES: dict[str, frozenset[str]] = {
    "COMMANDS.md": frozenset(
        {
            "2093af2b65705fec312e1e3c1dcd3bc2b14c4758dcdb3647d0b14c83a0b10252",
            "f7ef0bae2b9c845bde5fcc1e2fc9a60009f6ae65c6c5a5d8a5eb86fa3ffac7a5",
        }
    ),
    ".github/copilot-instructions.md": frozenset({"48d3e3409ec4cdec741d6e96e77442885e8f68f5c41369a1813bb47d6611bf14"}),
    ".github/workflows/linkedin.yml": frozenset({"137800248974efe3c41ddbc46c9364603077ed5e8d8711b217809acf164e39da"}),
    ".github/workflows/browser-hunt.yml": frozenset(
        {"c7abfb714150166ca899ab7541d7bbb5886a26bb3836920fb9b14802435c5e82"}
    ),
}

# old config path -> new config path. Both are user-layer YAML with the same
# `companies:` schema; the rename carries content forward so the normal
# update_workspace_assets() YAML deep-merge can reconcile it against the
# current template.
_RENAMED_CONFIG_FILES: dict[str, str] = {
    "config/companies_browser.yml": "config/career_pages.yml",
}
_RENAME_SOURCE_KNOWN_HASHES: frozenset[str] = frozenset(
    {"1948ee0365eb9fd2dda3163b54bc7affc5dc24bbb216fab8ccfce1a70088691a"}
)


@dataclass
class BridgeMigrationResult:
    removed: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.removed or self.renamed)


def run_bridge_migration(workspace: Path, *, dry_run: bool = False) -> BridgeMigrationResult:
    """Remove obsolete pre-refactor files/carry forward renamed config.

    Idempotent: files already gone or already renamed are simply skipped, so
    running this again after a successful update is a no-op.
    """
    workspace = workspace.resolve()
    result = BridgeMigrationResult(dry_run=dry_run)

    for rel, known_hashes in _OBSOLETE_FILES.items():
        _handle_obsolete_file(workspace, rel, known_hashes, result, dry_run)

    for old_rel, new_rel in _RENAMED_CONFIG_FILES.items():
        _handle_renamed_config(workspace, old_rel, new_rel, result, dry_run)

    return result


def _handle_obsolete_file(
    workspace: Path,
    rel: str,
    known_hashes: frozenset[str],
    result: BridgeMigrationResult,
    dry_run: bool,
) -> None:
    path = workspace / rel
    if not path.is_file() or is_protected(rel):
        return

    if sha256_file(path) in known_hashes:
        result.removed.append(rel)
        prefix = "[dry-run]" if dry_run else "[ok]"
        typer.echo(f"{prefix} Removed obsolete file: {rel}")
        if not dry_run:
            path.unlink()
    else:
        result.preserved.append(rel)
        typer.echo(f"[warn] Preserved modified obsolete file: {rel}")


def _handle_renamed_config(
    workspace: Path,
    old_rel: str,
    new_rel: str,
    result: BridgeMigrationResult,
    dry_run: bool,
) -> None:
    old_path = workspace / old_rel
    if not old_path.is_file() or is_protected(old_rel) or is_protected(new_rel):
        return

    new_path = workspace / new_rel
    if not new_path.is_file():
        result.renamed.append((old_rel, new_rel))
        prefix = "[dry-run]" if dry_run else "[ok]"
        typer.echo(f"{prefix} Migrated {old_rel} -> {new_rel}")
        if not dry_run:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            new_path.write_bytes(old_path.read_bytes())
            old_path.unlink()
        return

    # new_rel already exists — never overwrite it. Only clean up old_rel, and
    # only if it still holds stock (unmodified) content with no user data.
    if sha256_file(old_path) in _RENAME_SOURCE_KNOWN_HASHES:
        result.removed.append(old_rel)
        prefix = "[dry-run]" if dry_run else "[ok]"
        typer.echo(f"{prefix} Removed obsolete file: {old_rel}")
        if not dry_run:
            old_path.unlink()
    else:
        result.preserved.append(old_rel)
        typer.echo(f"[warn] Preserved modified obsolete file: {old_rel} (already migrated to {new_rel})")
