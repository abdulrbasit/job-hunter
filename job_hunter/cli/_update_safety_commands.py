"""Update-safety CLI commands."""

from __future__ import annotations

import typer

from job_hunter.cli import update_safety_app


@update_safety_app.command("classify")
def update_safety_classify(
    paths: list[str] = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Classify file paths by update safety layer."""
    from job_hunter.update_safety import classify_paths
    from job_hunter.ux.health import dump_json

    payload = {"paths": classify_paths(paths)}
    if json_output:
        typer.echo(dump_json(payload))
    else:
        for item in payload["paths"]:
            typer.echo(f"{item['layer']:<7} {item['path']}")


@update_safety_app.command("report")
def update_safety_report_cmd(
    paths: list[str] = typer.Argument(default=None),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show full update-safety report for given paths."""
    from job_hunter.tracker import repo_path
    from job_hunter.update_safety import update_safety_report
    from job_hunter.ux.health import dump_json

    payload = update_safety_report(
        repo_path(),
        paths=paths or None,
    )
    if json_output:
        typer.echo(dump_json(payload))
    else:
        for item in payload["paths"]:
            typer.echo(f"{item['layer']:<7} {item['path']}")
        if payload["unsafe"]:
            typer.echo("[update-safety] refused user/unknown paths:", err=True)
            for path in payload["unsafe"]:
                typer.echo(f"- {path}", err=True)
    raise typer.Exit(0 if payload["ok"] else 1)
