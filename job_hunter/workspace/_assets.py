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
_AGENT_SKILL_CLI_PREFIXES: tuple[str, ...] = (".agents", ".gemini")
_CANONICAL_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "README.md",
)
# Files/dirs that only exist in the bundled template (no canonical root counterpart).
# .gitignore: workspace version differs from the dev repo .gitignore.
_RESOURCE_ONLY_FILES: frozenset[str] = frozenset({".gitignore", "COMMANDS.md"})
_RESOURCE_ONLY_PREFIXES: tuple[str, ...] = (".env.example", ".github", ".vscode/", "outputs/", "profile/")

# Dev-only skills — excluded from the user workspace template.
_DEV_SKILL_DIRS: frozenset[str] = frozenset({"code", "commit", "dev-skills", "dev-tools", "refactor", "test"})


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


def iter_packaged_resource_files() -> Iterator[tuple[str, bytes]]:
    """Yield the wheel/package resource copy of workspace assets."""
    yield from _iter_resource_files(workspace_assets_root())


def _iter_source_checkout_files(root: Path) -> Iterator[tuple[str, bytes]]:
    yielded: set[str] = set()

    for rel in _CANONICAL_FILES:
        path = root / rel
        if path.is_file():
            yielded.add(rel)
            yield rel, path.read_bytes()

    for rel_dir in _CANONICAL_DIRS:
        path = root / rel_dir
        if path.is_dir():
            for rel, content in _walk_path(path, rel_dir):
                parts = rel.split("/")
                # Skip dev-only skills — not user-facing.
                if parts[:2] == [".claude", "skills"] and len(parts) > 2 and parts[2] in _DEV_SKILL_DIRS:
                    continue
                # Skip config/schemas/ — developer validation artifact, not user-facing.
                if parts[:2] == ["config", "schemas"]:
                    continue
                yielded.add(rel)
                yield rel, content

    template_profile = root / "profile" / "template-files"
    if template_profile.is_dir():
        for rel, content in _walk_path(template_profile, "profile"):
            yielded.add(rel)
            yield rel, content

    state_file = root / "outputs" / "state" / "discovered_urls.yml"
    if state_file.is_file():
        rel = "outputs/state/discovered_urls.yml"
        yielded.add(rel)
        yield rel, state_file.read_bytes()

    # Workspace-only files come from the bundled template (no canonical root counterpart).
    for rel, content in iter_packaged_resource_files():
        if rel in yielded:
            continue
        if rel in _RESOURCE_ONLY_FILES or rel.startswith(_RESOURCE_ONLY_PREFIXES):
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
