"""Dashboard, analytics, doctor, and verify CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from job_hunter.cli.app import app, internal_app
from job_hunter.cli.options import JSON_OPTION, WORKSPACE_OPTION


@app.command()
def dash() -> None:
    """Open the native web dashboard."""
    from job_hunter.config.loader import ROOT
    from job_hunter.ux.web import launch

    launch(ROOT)


@internal_app.command()
def analytics(
    days: int = typer.Option(30, "--days"),
    json_output: bool = JSON_OPTION,
) -> None:
    """Show pipeline analytics (JSON — internal/automation use; see the desktop app for the GUI view)."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.analytics import analyze_pipeline
    from job_hunter.ux.health import dump_json

    payload = analyze_pipeline(repo_path(), days=days)
    typer.echo(dump_json(payload))


@app.command()
def doctor(
    workspace: str = WORKSPACE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run health checks on the workspace and report setup status."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.health import doctor as run_doctor
    from job_hunter.ux.health import dump_json

    ws = repo_path() if workspace == "." else Path(workspace)
    payload = run_doctor(ws)
    if json_output:
        typer.echo(dump_json(payload))
    else:
        for check in payload["checks"]:
            mark = "OK  " if check["ok"] else "FAIL"
            typer.echo(f"{mark} {check['name']} - {check.get('detail', '')}")
            if not check["ok"] and check.get("fix"):
                typer.echo(f"     fix: {check['fix']}")
    raise typer.Exit(0 if payload["ok"] else 1)


@internal_app.command()
def verify(
    json_output: bool = JSON_OPTION,
) -> None:
    """Verify repository integrity."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.health import dump_json, verify_repository

    payload = verify_repository(repo_path())
    if json_output:
        typer.echo(dump_json(payload))
    else:
        for warning in payload["warnings"]:
            typer.echo(f"WARN {warning}")
        for error in payload["errors"]:
            typer.echo(f"FAIL {error}", err=True)
        if payload["ok"]:
            typer.echo("[verify] ok")
    raise typer.Exit(0 if payload["ok"] else 1)
