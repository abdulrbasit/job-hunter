"""Update workspace agent skills from the installed package template."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import typer

from job_hunter.workspace._assets import _AGENT_SKILL_CLI_PREFIXES, iter_managed_files

_SKILLS_PREFIXES = (".claude/skills/",) + tuple(f"{c}/skills/" for c in _AGENT_SKILL_CLI_PREFIXES)


@dataclass
class SkillsUpdateResult:
    written: list[str] = field(default_factory=list)


def iter_template_skill_files() -> list[tuple[str, bytes]]:
    """Return bundled skill files as workspace-relative paths (all agent CLIs)."""
    return [(p, c) for p, c in iter_managed_files() if any(p.startswith(pfx) for pfx in _SKILLS_PREFIXES)]


def update_skills(workspace: Path) -> SkillsUpdateResult:
    """Copy bundled skill files into a workspace for all supported agent CLIs."""
    workspace = workspace.resolve()
    result = SkillsUpdateResult()

    for rel_path, content in iter_template_skill_files():
        dest = workspace / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        result.written.append(rel_path)

    typer.echo(f"[ok] Updated {len(result.written)} skill file(s) in {workspace / '.claude' / 'skills'}")
    return result
