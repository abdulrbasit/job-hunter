#!/usr/bin/env python3
"""Sync user-facing files from the canonical repo root into job_hunter/templates/workspace/.

Run before `uv build` or whenever canonical root files change. Root-sourced
sections are only written by this script; workspace-only sections are maintained
directly under job_hunter/templates/workspace/.

Files NOT synced (workspace-only, maintained directly in the template):
  .env.example
  .github/workflows/find-jobs.yml
  .github/workflows/tailor-job.yml
  .gitignore           (workspace .gitignore differs from the dev repo .gitignore)
  outputs/             (empty-dir scaffolding with .gitkeep + discovered_urls.yml)
  profile/             (canonical starter profile and resume templates)
  SETUP.md, SETUP_AGENT.md, SETUP_LLM_API.md   (no root counterpart; edited directly)
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "job_hunter" / "templates" / "workspace"

_ROOT_FILES = [
    "CLAUDE.md",  # workspace copy is identical: @./AGENTS.md
    "GEMINI.md",  # workspace copy is identical: @./AGENTS.md
]

_ROOT_DIRS = [
    "config",
]

# Files within _ROOT_DIRS that are workspace-only and must NOT be synced.
# job_hunter.yml: template ships with blank defaults; root copy has personal data.
_SKIP_IN_DIRS: frozenset[str] = frozenset({"config/job_hunter.yml"})

# Dev-only skills — must match _DEV_SKILL_DIRS in job_hunter/workspace/_assets.py
_DEV_SKILL_DIRS = frozenset({"code", "commit", "dev-skills", "dev-tools", "refactor", "test"})


def _user_skills() -> list[str]:
    """Return skill directory names under .claude/skills/ that are user-facing."""
    skills_root = REPO / ".claude" / "skills"
    return sorted(d.name for d in skills_root.iterdir() if d.is_dir() and d.name not in _DEV_SKILL_DIRS)


def _sync_items(
    items: list[tuple[Path, Path, str]],
    dry_run: bool,
    changes: list[int],
) -> None:
    """Sync a list of (src, dst, label) file pairs.

    Compares src vs dst bytes, increments changes[0] for each difference, and
    either copies (normal mode) or reports (dry-run / check mode).
    """
    for src, dst, label in items:
        if dst.is_file() and filecmp.cmp(str(src), str(dst), shallow=False):
            continue
        changes[0] += 1
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  synced  {label}")
        else:
            print(f"  stale   {label}")


def sync(*, check: bool = False) -> int:  # noqa: C901
    """Sync canonical root → template. Returns count of files that differ (or would change)."""
    changes = [0]

    # Root files
    items: list[tuple[Path, Path, str]] = []
    for name in _ROOT_FILES:
        src = REPO / name
        if not src.is_file():
            print(f"  warn: {name} not found in repo root, skipping")
            continue
        items.append((src, TEMPLATE / name, name))
    _sync_items(items, check, changes)

    # Root dirs
    for name in _ROOT_DIRS:
        src = REPO / name
        if not src.is_dir():
            print(f"  warn: {name}/ not found in repo root, skipping")
            continue
        items = []
        for child in sorted(src.rglob("*")):
            if not child.is_file():
                continue
            rel = child.relative_to(src)
            label = f"{name}/{rel.as_posix()}"
            if label in _SKIP_IN_DIRS:
                continue
            items.append((child, TEMPLATE / name / rel, label))
        _sync_items(items, check, changes)

    # User skills
    skills_src = REPO / ".claude" / "skills"
    skills_dst = TEMPLATE / ".claude" / "skills"
    for skill in _user_skills():
        src = skills_src / skill
        if not src.is_dir():
            print(f"  warn: .claude/skills/{skill}/ not found, skipping")
            continue
        items = []
        for child in sorted(src.rglob("*")):
            if not child.is_file():
                continue
            rel = child.relative_to(src)
            items.append((child, skills_dst / skill / rel, f".claude/skills/{skill}/{rel.as_posix()}"))
        _sync_items(items, check, changes)

    return changes[0]


def main() -> None:
    check_mode = "--check" in sys.argv
    if check_mode:
        print("Checking workspace template is up to date...")
        n = sync(check=True)
        if n:
            print(f"\n{n} file(s) out of sync. Run: python scripts/sync_workspace_template.py")
            sys.exit(1)
        else:
            print("ok: workspace template is up to date")
    else:
        print("Syncing workspace template...")
        n = sync(check=False)
        if n:
            print(f"\nDone — {n} file(s) updated.")
        else:
            print("Done — already up to date.")


if __name__ == "__main__":
    main()
