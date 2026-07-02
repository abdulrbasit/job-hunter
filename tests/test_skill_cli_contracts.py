"""Verify `job-hunter internal ...` command snippets referenced by skill markdown
actually exist as registered CLI commands, and that referenced mode files exist.

Scans .claude/skills/**/*.md (source of truth) — the workspace template copy's
byte-identical-mirror is already asserted elsewhere (test_skill_contracts.py).
"""

from __future__ import annotations

import re
from pathlib import Path

from job_hunter.cli.app import agent_context_app, internal_app, linkedin_app, update_safety_app

ROOT = Path(__file__).resolve().parents[1]
_SKILL_FILES = sorted((ROOT / ".claude" / "skills").rglob("*.md"))

# `job-hunter internal <command>` or `job-hunter internal <group> <command>`.
# The second group only matches a lowercase-leading token, so CLI flags like
# `--phase` are never mistaken for a nested subcommand name.
_COMMAND_PATTERN = re.compile(r"job-hunter internal ([a-z][\w-]*)(?:\s+([a-z][\w-]*))?")


def _registered_names(typer_app) -> set[str]:
    return {cmd.name or cmd.callback.__name__ for cmd in typer_app.registered_commands}


def _registered_groups(typer_app) -> dict[str, object]:
    groups = {"agent-context": agent_context_app, "linkedin": linkedin_app, "update-safety": update_safety_app}
    return {grp.name: groups[grp.name] for grp in typer_app.registered_groups if grp.name in groups}


def _referenced_internal_commands() -> set[tuple[str, str, int]]:
    """Return (top_level_token, nested_token_or_empty, line_no) for every skill file match."""
    found: set[tuple[str, str, int, str]] = set()
    for path in _SKILL_FILES:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in _COMMAND_PATTERN.finditer(line):
                top, nested = match.group(1), match.group(2) or ""
                found.add((top, nested, line_no, path.as_posix()))
    return found


def test_skill_referenced_internal_commands_exist() -> None:
    top_level = _registered_names(internal_app)
    groups = _registered_groups(internal_app)

    offenders: list[str] = []
    for top, nested, line_no, path in _referenced_internal_commands():
        if top in groups:
            if nested and nested not in _registered_names(groups[top]):
                offenders.append(f"{path}:{line_no}: `internal {top} {nested}` — no such command in group '{top}'")
        elif top not in top_level:
            offenders.append(f"{path}:{line_no}: `internal {top}` — no such internal command")

    assert offenders == [], "\n".join(offenders)


def test_skill_referenced_mode_files_exist() -> None:
    """Skill routing (`execute .../modes/<name>.md inline`) must point at real files."""
    pattern = re.compile(r"`?\.claude/skills/([\w-]+)/modes/([\w-]+)\.md`?")
    offenders: list[str] = []
    for path in _SKILL_FILES:
        text = path.read_text(encoding="utf-8")
        for skill_dir, mode_name in pattern.findall(text):
            mode_path = ROOT / ".claude" / "skills" / skill_dir / "modes" / f"{mode_name}.md"
            if not mode_path.exists():
                offenders.append(f"{path.as_posix()}: references missing {mode_path.as_posix()}")

    assert offenders == [], "\n".join(offenders)
