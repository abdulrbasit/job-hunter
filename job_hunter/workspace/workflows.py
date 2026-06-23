"""Update workspace GitHub Actions workflows from the installed package template."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import typer

from job_hunter.workspace._assets import iter_managed_files

_WORKFLOW_PREFIXES = (".github/",)


@dataclass
class WorkflowsUpdateResult:
    written: list[str] = field(default_factory=list)


def iter_template_workflow_files() -> list[tuple[str, bytes]]:
    """Return bundled .github/ files as workspace-relative paths."""
    return [(p, c) for p, c in iter_managed_files() if any(p.startswith(pfx) for pfx in _WORKFLOW_PREFIXES)]


def _preserve_user_schedule(existing_text: str, new_text: str) -> str:
    """If existing workflow has active (uncommented) cron lines, carry them into the new file."""
    if not re.search(r"^\s+- cron:", existing_text, re.MULTILINE):
        return new_text

    schedule_match = re.search(r"( {2}schedule:\n(?:    - cron:.*\n)+)", existing_text)
    if not schedule_match:
        return new_text

    schedule_block = schedule_match.group(1)

    # Replace the commented-out schedule block in the template with the user's active schedule.
    new_text = re.sub(
        r"  # Uncomment.*?\n(?:  #.*\n)*?(?=  workflow_dispatch:)",
        schedule_block,
        new_text,
    )
    return new_text


def update_workflows(workspace: Path) -> WorkflowsUpdateResult:
    """Copy bundled .github/ files into a workspace, preserving user cron schedules."""
    workspace = workspace.resolve()
    result = WorkflowsUpdateResult()

    for rel_path, content in iter_template_workflow_files():
        dest = workspace / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        new_text = content.decode("utf-8")
        if dest.is_file() and rel_path == ".github/workflows/find-jobs.yml":
            new_text = _preserve_user_schedule(dest.read_text(encoding="utf-8"), new_text)

        dest.write_bytes(new_text.encode("utf-8"))
        result.written.append(rel_path)

    typer.echo(f"[ok] Updated {len(result.written)} workflow file(s) in {workspace / '.github'}")
    return result
