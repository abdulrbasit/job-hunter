"""One-time, lossless workspace config migrations."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from job_hunter.core.builtin_filters import LANG_CODE_TO_NAME

_FILTER_MAP = {
    "companies": "excluded_companies",
    "title_terms": "excluded_titles",
    "industries": "excluded_industries",
}


@dataclass(frozen=True)
class MigrationResult:
    migrated: bool
    message: str = ""


def _merge_values(existing: list[Any], values: list[Any]) -> list[str]:
    result = [str(value).strip() for value in existing if str(value).strip()]
    seen = {value.casefold() for value in result}
    result.extend(
        str(value).strip() for value in values if str(value).strip() and str(value).strip().casefold() not in seen
    )
    return result


def _atomic_write(path: Path, content: str) -> None:
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def migrate_legacy_exclusions(root: Path) -> MigrationResult:
    """Move legacy exclusions into standardized filter groups once.

    Migration is intentionally the only code path allowed to rewrite this protected
    config file. Exact original bytes are backed up before replacement.
    """
    path = root / "config" / "job_hunter.yml"
    if not path.exists():
        return MigrationResult(False)
    original = path.read_bytes()
    data = yaml.safe_load(original) or {}
    if not isinstance(data, dict) or "exclusions" not in data:
        return MigrationResult(False)

    exclusions = data.get("exclusions") or {}
    filters = data.setdefault("filters", {})
    for legacy_name, filter_name in _FILTER_MAP.items():
        filters[filter_name] = _merge_values(filters.get(filter_name, []) or [], exclusions.get(legacy_name, []) or [])

    excluded_languages = [str(value).casefold() for value in exclusions.get("languages", []) or []]
    canonical_codes: list[str] = []
    seen_names: set[str] = set()
    for code, name in LANG_CODE_TO_NAME.items():
        if name not in seen_names and name not in excluded_languages:
            canonical_codes.append(code)
            seen_names.add(name)
    filters["hunt_languages"] = _merge_values(filters.get("hunt_languages", []) or [], canonical_codes)

    data.pop("exclusions", None)
    backup = root / "outputs" / "state" / "config_backups" / "pre_filters_job_hunter.yml.bak"
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        _atomic_write(backup, original.decode("utf-8"))
    _atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return MigrationResult(True, "Migrated legacy exclusions into config/job_hunter.yml filters.")


def migrate_workspace_filter_files(root: Path) -> MigrationResult:
    """Fold obsolete config/filters files into job_hunter.yml, then remove them."""
    config_dir = root / "config"
    filters_dir = config_dir / "filters"
    filter_schema = config_dir / "schemas" / "filter.schema.json"
    if not filters_dir.exists() and not filter_schema.exists():
        return MigrationResult(False)

    path = config_dir / "job_hunter.yml"
    original = path.read_bytes() if path.exists() else b"{}\n"
    data = yaml.safe_load(original) or {}
    if not isinstance(data, dict):
        raise ValueError("config/job_hunter.yml must be a mapping before filter-file cleanup")

    if filters_dir.exists():
        unexpected = [
            item for item in filters_dir.iterdir() if not item.is_file() or item.suffix not in {".yml", ".yaml"}
        ]
        if unexpected:
            raise ValueError(
                f"Cannot remove config/filters with unsupported entries: {', '.join(item.name for item in unexpected)}"
            )

        from job_hunter.filters import FILTER_TYPES, canonicalize_filter_config

        canonical = canonicalize_filter_config(data)
        merged = dict(canonical.get("filters") or {})
        for file_path in sorted(filters_dir.iterdir()):
            name = file_path.stem
            canonical_name = "hunt_languages" if name == "languages" else name
            if canonical_name not in FILTER_TYPES:
                raise ValueError(f"Unknown workspace filter file: {file_path.name}")
            raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or []
            incoming = canonicalize_filter_config({"filters": {name: raw}})["filters"].get(canonical_name, [])
            merged[canonical_name] = _merge_values(merged.get(canonical_name, []), incoming)
        data["filters"] = merged

        backup = root / "outputs" / "state" / "config_backups" / "pre_filter_files_job_hunter.yml.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            _atomic_write(backup, original.decode("utf-8"))
        _atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        shutil.rmtree(filters_dir)

    if filter_schema.exists():
        filter_schema.unlink()
    return MigrationResult(True, "Folded obsolete workspace filter files into config/job_hunter.yml.")
