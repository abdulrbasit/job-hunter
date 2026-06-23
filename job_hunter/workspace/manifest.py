"""Workspace manifest — tracks managed file hashes and protected paths."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

MANIFEST_PATH = ".job-hunter/manifest.json"
WORKSPACE_VERSION = "1.0"

PROTECTED_PATHS: list[str] = [
    ".env",
    "config/job_hunter.yml",
    "profile/",
    "outputs/",
    "CLAUDE.local.md",
    "AGENTS.local.md",
    "GEMINI.local.md",
    "CODEX.local.md",
]


@dataclass
class WorkspaceManifest:
    workspace_version: str = WORKSPACE_VERSION
    package_version_created_with: str = "unknown"
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    managed_files: dict[str, str] = field(default_factory=dict)
    protected_paths: list[str] = field(default_factory=lambda: list(PROTECTED_PATHS))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> WorkspaceManifest:
        return cls(
            workspace_version=data.get("workspace_version", WORKSPACE_VERSION),
            package_version_created_with=data.get("package_version_created_with", "unknown"),
            generated_at=data.get("generated_at", ""),
            managed_files=data.get("managed_files", {}),
            protected_paths=data.get("protected_paths", list(PROTECTED_PATHS)),
        )


def sha256_file(path: Path) -> str:
    """Return hex SHA-256 of file content."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_protected(rel_path: str) -> bool:
    """True if rel_path is a protected user file."""
    rel = rel_path.replace("\\", "/")
    for p in PROTECTED_PATHS:
        if p.endswith("/"):
            if rel == p.rstrip("/") or rel.startswith(p):
                return True
        else:
            if rel == p:
                return True
    return False


def read_manifest(workspace: Path) -> WorkspaceManifest:
    """Read .job-hunter/manifest.json from workspace. Raises FileNotFoundError if missing."""
    path = workspace / MANIFEST_PATH
    if not path.exists():
        raise FileNotFoundError(f"No workspace manifest found at {path}. Run 'job-hunter init' first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return WorkspaceManifest.from_dict(data)


def write_manifest(workspace: Path, manifest: WorkspaceManifest) -> None:
    """Write .job-hunter/manifest.json to workspace."""
    path = workspace / MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")


def find_workspace_root(start: Path | None = None) -> Path | None:
    """Walk up from start looking for .job-hunter/manifest.json."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / MANIFEST_PATH).exists():
            return parent
        if (parent / "config" / "job_hunter.yml").exists():
            return parent
    return None


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("job-hunter")
    except Exception:
        return "unknown"
