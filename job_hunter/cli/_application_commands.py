"""Application lifecycle CLI commands."""

from __future__ import annotations

import typer

from job_hunter.cli import applications_app


@applications_app.command("list")
def applications_list(
    status: str | None = typer.Option(None, "--status"),
    region: str | None = typer.Option(None, "--region"),
    since: str | None = typer.Option(None, "--since"),
) -> None:
    """List applications, optionally filtered."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.applications import filtered_applications, render_applications_table

    apps = filtered_applications(root=repo_path(), status=status, region=region, since=since)
    typer.echo(render_applications_table(apps))


@applications_app.command("update")
def applications_update(
    job: str = typer.Argument(...),
    status: str = typer.Argument(...),
    note: str | None = typer.Option(None, "--note"),
) -> None:
    """Update an application's lifecycle status."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.applications import update_application_status

    app_rec = update_application_status(job, status, root=repo_path(), note=note)
    typer.echo(f"[applications] {app_rec['slug']} -> {app_rec['status']}")
