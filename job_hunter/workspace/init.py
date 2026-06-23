"""job-hunter init — create a new workspace from bundled assets."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

from job_hunter.workspace._assets import iter_managed_files
from job_hunter.workspace.manifest import (
    WORKSPACE_VERSION,
    WorkspaceManifest,
    _package_version,
    sha256_bytes,
    write_manifest,
)
from job_hunter.workspace.skills import _SKILLS_PREFIXES

_EMPTY_DIRS = [
    "outputs/state",
    "outputs/candidates",
    "outputs/jobs",
    "outputs/linkedin",
]


def run_init(path: Path, force: bool = False) -> None:
    """Create a new job-hunter workspace at path."""
    workspace = path.resolve()

    if workspace.exists() and any(workspace.iterdir()):
        if not force:
            typer.echo(
                f"[error] {workspace} already exists and is not empty.\n  Use --force to reinitialise anyway.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"[warn] --force: reinitialising existing workspace at {workspace}")

    workspace.mkdir(parents=True, exist_ok=True)
    managed: dict[str, str] = {}

    # Copy all managed assets
    for rel_path, content in iter_managed_files():
        dest = workspace / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        if any(rel_path.startswith(p) for p in _SKILLS_PREFIXES):
            managed[rel_path] = sha256_bytes(content)

    # Promote example configs to live configs (only when missing)
    _promote_examples(workspace)

    # Create required empty directories
    for d in _EMPTY_DIRS:
        (workspace / d).mkdir(parents=True, exist_ok=True)
        gitkeep = workspace / d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    # Write manifest
    manifest = WorkspaceManifest(
        workspace_version=WORKSPACE_VERSION,
        package_version_created_with=_package_version(),
        managed_files=managed,
    )
    write_manifest(workspace, manifest)

    typer.echo(f"\n[ok] Workspace created at: {workspace}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {workspace}")
    typer.echo("  cp .env.example .env  # then fill in your API keys")
    typer.echo("  job-hunter doctor")
    typer.echo("  job-hunter hunt --region primary")


def _promote_examples(workspace: Path) -> None:
    """Copy config/*.example.yml → config/*.yml when the live file doesn't exist yet."""
    config_dir = workspace / "config"
    for example in config_dir.glob("*.example.yml"):
        live = config_dir / example.name.replace(".example", "")
        if not live.exists():
            shutil.copy2(example, live)
