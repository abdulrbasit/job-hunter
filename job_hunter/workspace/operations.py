"""Workspace setup operations: init, update-skills, update-workflows.

Plain service layer — no CLI imports. Functions return result objects
(or raise WorkspaceNotEmptyError); cli/commands/update.py renders them.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

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
    removed_stale: list[str] = field(default_factory=list)
    preserved_modified: list[str] = field(default_factory=list)


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
                result.removed_stale.append(rel)
            elif dest.is_file():
                result.preserved_modified.append(rel)
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

    return result


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

_WORKFLOW_PREFIXES = (".github/",)


@dataclass
class WorkflowsUpdateResult:
    written: list[str] = field(default_factory=list)
    customized: list[str] = field(default_factory=list)


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
    """Copy bundled .github/ files into a workspace, preserving user cron schedules.

    Also tracks each workflow file's hash in the manifest. find-jobs.yml's schedule is
    preserved by _preserve_user_schedule above and is always safe to update past that.
    Other workflow files (tailor-job.yml) have no such merge logic — if the on-disk file
    differs from what was last installed here, the user has customized it (timeout,
    added env var, etc.). It's still updated, so fixes keep landing, but the file is
    reported back in `customized` instead of the edit being silently discarded.
    """
    workspace = workspace.resolve()
    result = WorkflowsUpdateResult()

    try:
        manifest = read_manifest(workspace)
    except FileNotFoundError:
        manifest = None

    new_managed: dict[str, str] = {}
    for rel_path, content in iter_template_workflow_files():
        dest = workspace / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        new_text = content.decode("utf-8")
        if dest.is_file():
            existing_bytes = dest.read_bytes()
            if rel_path == ".github/workflows/find-jobs.yml":
                new_text = _preserve_user_schedule(existing_bytes.decode("utf-8"), new_text)
            else:
                last_hash = manifest.managed_files.get(rel_path) if manifest else None
                if last_hash and sha256_bytes(existing_bytes) != last_hash:
                    result.customized.append(rel_path)

        dest.write_bytes(new_text.encode("utf-8"))
        result.written.append(rel_path)
        new_managed[rel_path] = sha256_bytes(new_text.encode("utf-8"))

    if manifest is not None:
        manifest.managed_files.update(new_managed)
        write_manifest(workspace, manifest)

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


class WorkspaceNotEmptyError(Exception):
    """Target directory exists and is not empty; caller must pass force=True to proceed."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        super().__init__(f"{workspace} already exists and is not empty")


@dataclass
class InitResult:
    workspace: Path
    reinitialized: bool = False
    telemetry_warnings: list[str] = field(default_factory=list)


def run_init(path: Path, force: bool = False) -> InitResult:
    """Create a new job-hunter workspace at path.

    Raises WorkspaceNotEmptyError when the target is non-empty and force is False.
    """
    workspace = path.resolve()

    reinitialized = False
    if workspace.exists() and any(workspace.iterdir()):
        if not force:
            raise WorkspaceNotEmptyError(workspace)
        reinitialized = True

    workspace.mkdir(parents=True, exist_ok=True)
    managed: dict[str, str] = {}

    for rel_path, content in iter_managed_files():
        dest = workspace / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        if any(rel_path.startswith(p) for p in _SKILLS_PREFIXES + _WORKFLOW_PREFIXES):
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
    warnings = install_telemetry(workspace)

    return InitResult(workspace=workspace, reinitialized=reinitialized, telemetry_warnings=warnings)


def install_telemetry(workspace: Path) -> list[str]:
    """Install telemetry hooks; returns human-readable warnings for any preserved conflicts."""
    from job_hunter.metrics.setup import configure_codex_telemetry, install_workspace_telemetry

    install_workspace_telemetry(workspace)
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    result = configure_codex_telemetry(codex_home / "config.toml")
    if result == "conflict":
        return ["Existing Codex OTel config preserved; Job Hunter token telemetry is not enabled for Codex."]
    if result == "invalid":
        return ["Invalid Codex config preserved; Job Hunter token telemetry is not enabled for Codex."]
    return []


def _promote_examples(workspace: Path) -> None:
    """Copy config/*.example.yml → config/*.yml when the live file doesn't exist yet."""
    config_dir = workspace / "config"
    for example in config_dir.glob("*.example.yml"):
        live = config_dir / example.name.replace(".example", "")
        if not live.exists():
            shutil.copy2(example, live)
