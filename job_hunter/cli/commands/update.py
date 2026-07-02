"""Workspace lifecycle CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from job_hunter.cli.app import app, internal_app
from job_hunter.cli.options import WORKSPACE_OPTION


def _echo_skills_result(result, workspace: Path) -> None:
    for rel in result.removed_stale:
        typer.echo(f"[ok] Removed stale skill: {rel}")
    for rel in result.preserved_modified:
        typer.echo(f"[warn] Preserved modified stale skill: {rel}")
    typer.echo(f"[ok] Updated {len(result.written)} skill file(s) in {workspace.resolve() / '.claude' / 'skills'}")


def _echo_workflows_result(result, workspace: Path) -> None:
    typer.echo(f"[ok] Updated {len(result.written)} workflow file(s) in {workspace.resolve() / '.github'}")


def _echo_telemetry_warnings(warnings: list[str]) -> None:
    for message in warnings:
        typer.echo(f"[warn] {message}")


@app.command()
def init(
    path: str = typer.Argument("job-hunter-workspace", help="Directory to create"),
    force: bool = typer.Option(False, "--force", "-f", help="Reinitialise a non-empty directory"),
) -> None:
    """Create a workspace with bundled assets."""
    from job_hunter.workspace.operations import WorkspaceNotEmptyError, run_init

    try:
        result = run_init(Path(path), force=force)
    except WorkspaceNotEmptyError as exc:
        typer.echo(
            f"[error] {exc.workspace} already exists and is not empty.\n  Use --force to reinitialise anyway.",
            err=True,
        )
        raise typer.Exit(1) from exc

    if result.reinitialized:
        typer.echo(f"[warn] --force: reinitialising existing workspace at {result.workspace}")
    _echo_telemetry_warnings(result.telemetry_warnings)
    typer.echo(f"\n[ok] Workspace created at: {result.workspace}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {result.workspace}")
    typer.echo("  job-hunter doctor")
    typer.echo("  # Open this folder in VS Code and run /setup onboard")
    typer.echo("  # Commit and push setup, then run GitHub Actions > Find Jobs")


@internal_app.command(name="update-skills")
def update_skills(workspace: str = WORKSPACE_OPTION) -> None:
    """Update bundled agent skills only."""
    from job_hunter.workspace.operations import update_skills as run_update_skills

    _echo_skills_result(run_update_skills(Path(workspace)), Path(workspace))


@internal_app.command(name="update-workflows")
def update_workflows(workspace: str = WORKSPACE_OPTION) -> None:
    """Update bundled GitHub workflows only."""
    from job_hunter.workspace.operations import update_workflows as run_update_workflows

    _echo_workflows_result(run_update_workflows(Path(workspace)), Path(workspace))


@app.command()
def update(
    workspace: str = typer.Option(".", "--workspace", "-w", help="Path to workspace"),
    skills_only: bool = typer.Option(False, "--skills-only", help="Update bundled agent skills only"),
    workflows_only: bool = typer.Option(False, "--workflows-only", help="Update GitHub workflows only"),
) -> None:
    """Update workspace assets after a package upgrade."""
    from job_hunter.workspace.assets import update_workspace_assets
    from job_hunter.workspace.operations import install_telemetry
    from job_hunter.workspace.operations import update_skills as run_update_skills
    from job_hunter.workspace.operations import update_workflows as run_update_workflows

    if skills_only and workflows_only:
        typer.echo("[update] choose at most one targeted update", err=True)
        raise typer.Exit(2)

    root = Path(workspace)
    if skills_only:
        _echo_skills_result(run_update_skills(root), root)
        return
    if workflows_only:
        _echo_workflows_result(run_update_workflows(root), root)
        return

    written = update_workspace_assets(root)
    typer.echo(f"[ok] Updated {len(written)} workspace asset(s)")
    _echo_skills_result(run_update_skills(root), root)
    _echo_workflows_result(run_update_workflows(root), root)
    _echo_telemetry_warnings(install_telemetry(root))


@app.command()
def version() -> None:
    """Show versions and package update guidance."""
    from job_hunter.config.loader import package_version
    from job_hunter.workspace.manifest import find_workspace_root, read_manifest

    typer.echo(f"job-hunter {package_version()}")
    workspace = find_workspace_root()
    if workspace:
        try:
            typer.echo(f"workspace {read_manifest(workspace).workspace_version}  ({workspace})")
        except Exception:
            typer.echo(f"workspace (no manifest)  ({workspace})")
    else:
        typer.echo("workspace not found (run 'job-hunter init' to create one)")

    typer.echo(
        "\nUpdate flow:\n"
        "  uv tool upgrade job-hunter-kit\n"
        "    or: pip install --upgrade job-hunter-kit\n"
        "\n  Then, in your workspace:\n"
        "  job-hunter update\n"
        "  job-hunter doctor\n"
    )
