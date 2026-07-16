"""One-time, lossless workspace config migrations."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from job_hunter.config.defaults import LANGUAGE_INDICATORS

_FILTER_MAP = {
    "companies": ("excluded_companies", "Companies excluded from results"),
    "title_terms": ("excluded_titles", "Title terms excluded from results"),
    "industries": ("excluded_industries", "Industries excluded from results"),
}


@dataclass(frozen=True)
class MigrationResult:
    migrated: bool
    message: str = ""


def _entries(values: list[Any]) -> list[dict[str, str]]:
    return [{"value": str(value)} for value in values if str(value).strip()]


def _merge_entries(filter_data: dict[str, Any], values: list[Any]) -> None:
    existing = filter_data.setdefault("entries", [])
    seen = {str(entry.get("value") or "").casefold() for entry in existing if isinstance(entry, dict)}
    existing.extend(entry for entry in _entries(values) if entry["value"].casefold() not in seen)


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
    for legacy_name, (filter_name, description) in _FILTER_MAP.items():
        filter_data = filters.setdefault(filter_name, {"description": description, "entries": []})
        _merge_entries(filter_data, exclusions.get(legacy_name, []) or [])

    excluded_languages = [str(value).casefold() for value in exclusions.get("languages", []) or []]
    known_languages = ["english", *LANGUAGE_INDICATORS]
    language_filter = filters.setdefault("languages", {"description": "Languages allowed during hunts", "entries": []})
    _merge_entries(language_filter, [name for name in known_languages if name not in excluded_languages])
    if excluded_languages:
        language_filter["description"] += f"; migrated legacy exclusions: {', '.join(excluded_languages)}"

    data.pop("exclusions", None)
    backup = root / "outputs" / "state" / "config_backups" / "pre_filters_job_hunter.yml.bak"
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        _atomic_write(backup, original.decode("utf-8"))
    _atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return MigrationResult(True, "Migrated legacy exclusions into config/job_hunter.yml filters.")
