"""Workspace setup operations: init, update-skills, update-workflows."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import typer

from job_hunter.workspace.assets import _AGENT_SKILL_CLI_PREFIXES, iter_managed_files
from job_hunter.workspace.manifest import (
    WORKSPACE_VERSION,
    WorkspaceManifest,
    _package_version,
    is_protected,
    read_manifest,
    sha256_bytes,
    write_manifest,
)

# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

_SKILLS_PREFIXES = (".claude/skills/",) + tuple(f"{c}/skills/" for c in _AGENT_SKILL_CLI_PREFIXES)


@dataclass
class SkillsUpdateResult:
    written: list[str] = field(default_factory=list)


def iter_template_skill_files() -> list[tuple[str, bytes]]:
    """Return bundled skill files as workspace-relative paths (all agent CLIs)."""
    return [(p, c) for p, c in iter_managed_files() if any(p.startswith(pfx) for pfx in _SKILLS_PREFIXES)]


def update_skills(workspace: Path) -> SkillsUpdateResult:
    """Copy bundled skill files into a workspace, deleting stale removed files."""
    workspace = workspace.resolve()
    result = SkillsUpdateResult()

    # Collect current template skills
    current_skills = {rel: content for rel, content in iter_template_skill_files()}

    # Delete skills that were previously managed but no longer exist in the template
    try:
        manifest = read_manifest(workspace)
        stale = set(manifest.managed_files.keys()) - set(current_skills.keys())
        for rel in sorted(stale):
            dest = workspace / rel
            unchanged = dest.is_file() and sha256_bytes(dest.read_bytes()) == manifest.managed_files[rel]
            if unchanged and not is_protected(rel):
                dest.unlink()
                typer.echo(f"[ok] Removed stale skill: {rel}")
            elif dest.is_file():
                typer.echo(f"[warn] Preserved modified stale skill: {rel}")
    except FileNotFoundError:
        pass  # no manifest — old workspace, skip cleanup

    # Write all current skills and update manifest
    new_managed: dict[str, str] = {}
    for rel_path, content in current_skills.items():
        dest = workspace / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        result.written.append(rel_path)
        new_managed[rel_path] = sha256_bytes(content)

    try:
        manifest = read_manifest(workspace)
        manifest.managed_files = new_managed
        write_manifest(workspace, manifest)
    except FileNotFoundError:
        pass  # no manifest — old workspace, skip

    typer.echo(f"[ok] Updated {len(result.written)} skill file(s) in {workspace / '.claude' / 'skills'}")
    return result


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

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

    for rel_path, content in iter_managed_files():
        dest = workspace / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        if any(rel_path.startswith(p) for p in _SKILLS_PREFIXES):
            managed[rel_path] = sha256_bytes(content)

    _promote_examples(workspace)

    for d in _EMPTY_DIRS:
        (workspace / d).mkdir(parents=True, exist_ok=True)
        gitkeep = workspace / d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    manifest = WorkspaceManifest(
        workspace_version=WORKSPACE_VERSION,
        package_version_created_with=_package_version(),
        managed_files=managed,
    )
    write_manifest(workspace, manifest)

    typer.echo(f"\n[ok] Workspace created at: {workspace}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {workspace}")
    typer.echo("  job-hunter doctor")
    typer.echo("  # Open this folder in VS Code and run /setup onboard")
    typer.echo("  # Commit and push setup, then run GitHub Actions > Find Jobs")


def _promote_examples(workspace: Path) -> None:
    """Copy config/*.example.yml → config/*.yml when the live file doesn't exist yet."""
    config_dir = workspace / "config"
    for example in config_dir.glob("*.example.yml"):
        live = config_dir / example.name.replace(".example", "")
        if not live.exists():
            shutil.copy2(example, live)
