"""Job Hunter CLI — Typer app and sub-app wiring. Command bodies live in cli/commands/."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="job-hunter",
    help="Job search automation — agent mode and LLM-API mode.",
    add_completion=False,
    no_args_is_help=True,
)

internal_app = typer.Typer(
    help="Commands used by bundled agent skills and maintenance automation.", no_args_is_help=True
)
app.add_typer(internal_app, name="internal", hidden=True)

agent_context_app = typer.Typer(help="Build agent context objects for Claude Code skills.", no_args_is_help=True)
internal_app.add_typer(agent_context_app, name="agent-context")

applications_app = typer.Typer(help="Manage application lifecycle.", no_args_is_help=True)
app.add_typer(applications_app, name="applications")

linkedin_app = typer.Typer(help="Run LinkedIn content and networking pipelines.", no_args_is_help=True)
internal_app.add_typer(linkedin_app, name="linkedin")

update_safety_app = typer.Typer(help="Classify paths by update safety layer.", no_args_is_help=True)
internal_app.add_typer(update_safety_app, name="update-safety")

# Side-effect imports: each module registers its commands on the typer apps above via decorators.
from job_hunter.cli import _agent_context as _agent_context_commands  # noqa: E402,F401
from job_hunter.cli.commands import applications as _applications_commands  # noqa: E402,F401
from job_hunter.cli.commands import dashboard as _dashboard_commands  # noqa: E402,F401
from job_hunter.cli.commands import hunt as _hunt_commands  # noqa: E402,F401
from job_hunter.cli.commands import internal as _internal_commands  # noqa: E402,F401
from job_hunter.cli.commands import linkedin as _linkedin_commands  # noqa: E402,F401
from job_hunter.cli.commands import tailor as _tailor_commands  # noqa: E402,F401
from job_hunter.cli.commands import telemetry as _telemetry_commands  # noqa: E402,F401
from job_hunter.cli.commands import update as _update_commands  # noqa: E402,F401
