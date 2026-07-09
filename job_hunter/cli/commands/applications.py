"""Application lifecycle CLI commands."""

from __future__ import annotations

import typer

from job_hunter.cli.app import applications_app


@applications_app.command("update")
def applications_update(
    job: str = typer.Argument(...),
    status: str = typer.Argument(...),
    note: str | None = typer.Option(None, "--note"),
) -> None:
    """Update an application's lifecycle status."""
    from datetime import date

    from job_hunter.pipeline.stages.readme import update_readme_from_applications
    from job_hunter.tracker import repo_path
    from job_hunter.tracking.applications import load_applications, update_application_status

    root = repo_path()
    app_rec = update_application_status(job, status, root=root, note=note)
    apps = load_applications(root)["applications"]
    update_readme_from_applications(apps, root, date.today().isoformat())
    typer.echo(f"[applications] {app_rec['slug']} -> {app_rec['status']}")
