"""Asset access helpers for workspace initialization.

In a source checkout, most workspace assets are read from canonical repo-root
files so contributors do not maintain a second hand-edited template copy. In an
installed wheel, those same assets are read from package resources generated for
distribution.
"""

from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

_CANONICAL_DIRS = (
    ".claude",
    "config",
)

# Agent CLIs that mirror .claude/skills/ at install time (no stored copies).
_AGENT_SKILL_CLI_PREFIXES: tuple[str, ...] = (".agents",)
_CANONICAL_FILES = ("CLAUDE.md",)  # workspace copy is byte-identical to root: "@./AGENTS.md"
# Obsolete agent CLI dirs removed from new installs and cleaned on update.
_OBSOLETE_CLI_DIRS: tuple[str, ...] = (".gemini",)
# Files/dirs that only exist in the bundled template (no canonical root counterpart).
# .gitignore: workspace version differs from the dev repo .gitignore.
# AGENTS.md/README.md: content genuinely diverges from the root copies (root = dev-repo
# context/product pitch, workspace = user-workspace context/applications tracker) — unlike
# CLAUDE.md, syncing these from root would ship the wrong document to a new workspace.
_RESOURCE_ONLY_FILES: frozenset[str] = frozenset(
    {
        ".gitignore",
        "AGENTS.md",
        "README.md",
        "SETUP.md",
        "SETUP_AGENT.md",
        "SETUP_LLM_API.md",
        "config/job_hunter.yml",
    }
)
_RESOURCE_ONLY_PREFIXES: tuple[str, ...] = (".env.example", ".github", ".vscode/", "outputs/", "profile/")

# Dev-only skills — excluded from the user workspace template.
_DEV_SKILL_DIRS: frozenset[str] = frozenset({"code", "commit", "dev-skills", "dev-tools", "refactor", "test"})
_UPDATE_ASSETS = (
    "README.md",
    "SETUP.md",
    "SETUP_AGENT.md",
    "SETUP_LLM_API.md",
    "config/schemas/job_hunter.schema.json",
)
_README_BLOCKS = (
    ("<!-- JOBS_STATS_START -->", "<!-- JOBS_STATS_END -->"),
    ("<!-- JOBS_TABLE_START -->", "<!-- JOBS_TABLE_END -->"),
)
# companies.db is a regenerable runtime cache (package seed + config/job_hunter.yml's
# companies.targets mirror) — never git-synced, unlike jobs.db.
_SQLITE_IGNORE_LINES = (
    "outputs/state/jobs.db-wal",
    "outputs/state/jobs.db-shm",
    "outputs/state/companies.db",
    "outputs/state/companies.db-wal",
    "outputs/state/companies.db-shm",
)


def workspace_assets_root() -> Traversable:
    """Return the bundled workspace template root."""
    return files("job_hunter.templates").joinpath("workspace")


def repo_root() -> Path:
    """Return the source checkout root when running from an editable checkout."""
    return Path(__file__).resolve().parents[2]


def _source_checkout_available() -> bool:
    root = repo_root()
    return (root / "pyproject.toml").exists() and (root / ".claude" / "skills").exists()


def iter_managed_files() -> Iterator[tuple[str, bytes]]:
    """Yield (relative_path_str, content_bytes) for every managed workspace asset."""
    source = (
        _iter_source_checkout_files(repo_root()) if _source_checkout_available() else iter_packaged_resource_files()
    )
    for path, content in source:
        yield path, content
        if path.startswith(".claude/skills/"):
            suffix = path[len(".claude/") :]  # "skills/job-hunter/SKILL.md"
            for cli in _AGENT_SKILL_CLI_PREFIXES:
                yield f"{cli}/{suffix}", content


def _preserve_readme_blocks(existing: bytes, template: bytes) -> bytes:
    """Return template README with generated stats/table copied from existing."""
    old = existing.decode()
    new = template.decode()
    for start, end in _README_BLOCKS:
        old_start, old_end = old.find(start), old.find(end)
        new_start, new_end = new.find(start), new.find(end)
        if min(old_start, old_end, new_start, new_end) < 0:
            continue
        block = old[old_start : old_end + len(end)]
        new = new[:new_start] + block + new[new_end + len(end) :]
    return new.encode()


def update_workspace_assets(workspace: Path) -> list[str]:
    """Update workspace assets: system docs overwritten; user-owned YAML configs left alone."""
    import shutil

    workspace = workspace.resolve()
    for cli in _OBSOLETE_CLI_DIRS:
        obsolete = workspace / cli
        if obsolete.is_dir():
            shutil.rmtree(obsolete)

    assets = dict(iter_packaged_resource_files())
    written: list[str] = []
    for rel in _UPDATE_ASSETS:
        dest = workspace.resolve() / rel
        # YAML configs are user-owned: back-fill only if missing, never overwrite.
        if rel.endswith(".yml") and dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = assets[rel]
        if rel == "README.md" and dest.exists():
            content = _preserve_readme_blocks(dest.read_bytes(), content)
        dest.write_bytes(content)
        written.append(rel)

    gitignore = workspace / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    missing = [line for line in _SQLITE_IGNORE_LINES if line not in existing.splitlines()]
    if missing:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        gitignore.write_text(existing + separator + "\n".join(missing) + "\n", encoding="utf-8")
    return written


def iter_packaged_resource_files() -> Iterator[tuple[str, bytes]]:
    """Yield the wheel/package resource copy of workspace assets."""
    yield from _iter_resource_files(workspace_assets_root())


def is_resource_only_file(rel: str) -> bool:
    """True when the workspace file has no canonical root counterpart — bundled template owns it."""
    return rel in _RESOURCE_ONLY_FILES or rel.startswith(_RESOURCE_ONLY_PREFIXES)


def is_dev_only_skill(rel: str) -> bool:
    """True for contributor-only skills that must not ship to user workspaces."""
    parts = rel.split("/")
    return parts[:2] == [".claude", "skills"] and len(parts) > 2 and parts[2] in _DEV_SKILL_DIRS


def _iter_canonical_files(root: Path) -> Iterator[tuple[str, bytes]]:
    """Yield workspace assets owned by canonical repo-root files (editable checkout only)."""
    for rel in _CANONICAL_FILES:
        path = root / rel
        if path.is_file():
            yield rel, path.read_bytes()

    for rel_dir in _CANONICAL_DIRS:
        path = root / rel_dir
        if not path.is_dir():
            continue
        for rel, content in _walk_path(path, rel_dir):
            if rel in _RESOURCE_ONLY_FILES or is_dev_only_skill(rel):
                continue
            yield rel, content

    state_file = root / "outputs" / "state" / "discovered_urls.yml"
    if state_file.is_file():
        yield "outputs/state/discovered_urls.yml", state_file.read_bytes()


def _iter_source_checkout_files(root: Path) -> Iterator[tuple[str, bytes]]:
    yielded: set[str] = set()
    for rel, content in _iter_canonical_files(root):
        yielded.add(rel)
        yield rel, content

    # Workspace-only files come from the bundled template (no canonical root counterpart).
    for rel, content in iter_packaged_resource_files():
        if rel not in yielded and is_resource_only_file(rel):
            yield rel, content


def _iter_resource_files(root: Traversable) -> Iterator[tuple[str, bytes]]:
    def walk(node: Traversable, prefix: str = "") -> Iterator[tuple[str, bytes]]:
        for child in sorted(node.iterdir(), key=lambda item: item.name):
            rel = f"{prefix}/{child.name}" if prefix else child.name
            if child.is_dir():
                yield from walk(child, rel)
            elif child.is_file():
                yield rel, child.read_bytes()

    yield from walk(root)


def _walk_path(root: Path, prefix: str) -> Iterator[tuple[str, bytes]]:
    for child in sorted(root.rglob("*")):
        if child.is_file():
            rel = f"{prefix}/{child.relative_to(root).as_posix()}"
            yield rel, child.read_bytes()
