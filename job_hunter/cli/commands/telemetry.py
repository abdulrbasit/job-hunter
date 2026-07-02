"""Hidden commands used by Claude Code/Codex telemetry hooks and skills."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from job_hunter.cli.app import internal_app
from job_hunter.metrics.telemetry import (
    active_run,
    begin_run,
    classify_job_hunter_mode,
    end_active_phase,
    end_run,
    record_outcome,
    start_phase,
    telemetry_status,
)
from job_hunter.workspace.manifest import find_workspace_root


def _root(workspace: str, payload: dict | None = None) -> Path:
    if workspace:
        return Path(workspace).resolve()
    cwd = Path(str((payload or {}).get("cwd") or Path.cwd()))
    return find_workspace_root(cwd) or cwd.resolve()


def _db(root: Path) -> Path:
    return root / "outputs" / "state" / "metrics.db"


@internal_app.command(name="telemetry-hook")
def telemetry_hook(
    backend: str = typer.Option(..., "--backend"),
    event: str = typer.Option(..., "--event"),
    workspace: str = typer.Option("", "--workspace"),
) -> None:
    """Receive lifecycle hook JSON on stdin; never block the agent."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        root = _root(workspace, payload)
        db_path = _db(root)
        session_id = str(payload.get("session_id") or "")
        if event == "prompt":
            from job_hunter.metrics.collector import ensure_collector

            ensure_collector(root)
            mode = classify_job_hunter_mode(str(payload.get("prompt") or ""))
            if mode and session_id:
                begin_run(
                    db_path,
                    backend=backend,
                    session_id=session_id,
                    mode=mode,
                    app_entrypoint=str(payload.get("app_entrypoint") or ""),
                )
        elif session_id:
            run_id = active_run(db_path, session_id)
            if run_id:
                last_message = str(payload.get("last_assistant_message") or "").lower()
                if event == "stop" and ("reply yes" in last_message or last_message.rstrip().endswith("?")):
                    return
                end_run(db_path, run_id, status="completed" if event == "stop" else "interrupted")
    except Exception:  # noqa: BLE001
        return


@internal_app.command(name="telemetry-mark")
def telemetry_mark(
    phase: str = typer.Option(..., "--phase"),
    state: str = typer.Option(..., "--state"),
    job: str = typer.Option("", "--job"),
    status: str = typer.Option("completed", "--status"),
    workspace: str = typer.Option("", "--workspace"),
) -> None:
    """Mark a skill phase boundary for token attribution."""
    try:
        root = _root(workspace)
        db_path = _db(root)
        run_id = active_run(db_path)
        if not run_id:
            return
        if state == "start":
            start_phase(db_path, run_id=run_id, phase=phase, job_slug=job)
        elif state == "end":
            end_active_phase(db_path, run_id, status=status)
    except Exception:  # noqa: BLE001
        return


@internal_app.command(name="telemetry-status")
def telemetry_status_command(
    workspace: str = typer.Option("", "--workspace"),
    as_json: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Print a privacy-safe telemetry diagnostic snapshot (no prompts/content)."""
    root = _root(workspace)
    status = telemetry_status(root)
    if as_json:
        typer.echo(json.dumps(status, indent=2, default=str))
    else:
        for key, value in status.items():
            typer.echo(f"{key}: {value}")


@internal_app.command(name="telemetry-outcome")
def telemetry_outcome(
    job: str = typer.Option(..., "--job"),
    decision: str = typer.Option("", "--decision"),
    tailored: bool = typer.Option(False, "--tailored"),
    failed: bool = typer.Option(False, "--failed"),
    workspace: str = typer.Option("", "--workspace"),
) -> None:
    """Record privacy-safe job outcomes for skill evaluation."""
    try:
        db_path = _db(_root(workspace))
        run_id = active_run(db_path)
        if run_id:
            record_outcome(
                db_path,
                run_id=run_id,
                job_slug=job,
                decision=decision,
                tailored=tailored,
                failed=failed,
            )
    except Exception:  # noqa: BLE001
        return
