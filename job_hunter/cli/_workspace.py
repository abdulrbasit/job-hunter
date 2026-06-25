"""Workspace lifecycle CLI commands."""

from pathlib import Path

import typer

from job_hunter.cli import app, internal_app


@app.command()
def init(
    path: str = typer.Argument("job-hunter-workspace", help="Directory to create"),
    force: bool = typer.Option(False, "--force", "-f", help="Reinitialise a non-empty directory"),
) -> None:
    """Create a workspace with bundled assets."""
    from job_hunter.workspace._ops import run_init

    run_init(Path(path), force=force)


@internal_app.command(name="update-skills")
def update_skills(workspace: str = typer.Option(".", "--workspace", "-w")) -> None:
    """Update bundled agent skills only."""
    from job_hunter.workspace._ops import update_skills as run_update_skills

    run_update_skills(Path(workspace))


@internal_app.command(name="update-workflows")
def update_workflows(workspace: str = typer.Option(".", "--workspace", "-w")) -> None:
    """Update bundled GitHub workflows only."""
    from job_hunter.workspace._ops import update_workflows as run_update_workflows

    run_update_workflows(Path(workspace))


@app.command()
def update(
    workspace: str = typer.Option(".", "--workspace", "-w", help="Path to workspace"),
    skills_only: bool = typer.Option(False, "--skills-only", help="Update bundled agent skills only"),
    workflows_only: bool = typer.Option(False, "--workflows-only", help="Update GitHub workflows only"),
) -> None:
    """Update workspace assets after a package upgrade."""
    from job_hunter.workspace._assets import update_workspace_assets
    from job_hunter.workspace._ops import update_skills as run_update_skills
    from job_hunter.workspace._ops import update_workflows as run_update_workflows

    if skills_only and workflows_only:
        typer.echo("[update] choose at most one targeted update", err=True)
        raise typer.Exit(2)

    root = Path(workspace)
    if skills_only:
        run_update_skills(root)
        return
    if workflows_only:
        run_update_workflows(root)
        return

    written = update_workspace_assets(root)
    typer.echo(f"[ok] Updated {len(written)} workspace asset(s)")
    run_update_skills(root)
    run_update_workflows(root)


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
