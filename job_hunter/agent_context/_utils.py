"""Shared utility helpers for agent_context sub-modules."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from job_hunter.tracker import repo_path


def _root(root: Path | None = None) -> Path:
    return root if root is not None else repo_path()


def _read_json_or_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text) or {}


def _clip(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    suffix = " ... [truncated]"
    if limit <= len(suffix):
        return suffix[:limit]
    return text[: limit - len(suffix)].rstrip() + suffix


def _resolve_path(root: Path, path: Path | str) -> Path:
    resolved = Path(path)
    return resolved if resolved.is_absolute() else root / resolved


def _prefer_compiled(path: Path, root: Path) -> Path:
    """Return the compiled counterpart of a profile file if it exists."""
    compiled = root / "outputs" / "state" / "compiled" / (path.stem + ".min" + path.suffix)
    return compiled if compiled.exists() else path
