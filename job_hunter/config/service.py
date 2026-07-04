"""Backend config service: safe read/validate/save/undo for user-editable config files.

Editable files (config/job_hunter.yml, config/career_pages.yml, profile/career_context.md)
are read and written as raw user content — never through get_job_hunter_config()'s merged
runtime defaults — so a save can never bake code-owned defaults into disk.

Every save is guarded by a SHA-256 revision token of the current file bytes (rejecting
stale saves), written through a same-directory temp file + fsync + os.replace, and backed
up to outputs/state/config_backups/ for one-level Undo.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from job_hunter.config.loader import get_job_hunter_config
from job_hunter.config.removed_keys import reject_removed_user_config

MAX_CAREER_CONTEXT_BYTES = 512 * 1024

JOB_HUNTER_CONFIG_REL = Path("config/job_hunter.yml")
CAREER_PAGES_REL = Path("config/career_pages.yml")
CAREER_CONTEXT_REL = Path("profile/career_context.md")

_BACKUP_DIR_REL = Path("outputs/state/config_backups")
_LOGICAL_FILES: dict[str, Path] = {
    "job_hunter_config": JOB_HUNTER_CONFIG_REL,
    "career_pages": CAREER_PAGES_REL,
    "career_context": CAREER_CONTEXT_REL,
}


def get_revision(path: Path) -> str:
    """SHA-256 hex digest of the file's current bytes (empty-file digest if missing)."""
    data = path.read_bytes() if path.exists() else b""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_job_hunter_yaml(data: Any, root: Path) -> list[str]:
    """Structural validation for job_hunter.yml: removed keys, then JSON schema."""
    if not isinstance(data, dict):
        return ["config must be a YAML mapping"]

    errors: list[str] = []
    try:
        reject_removed_user_config(data)
    except ValueError as exc:
        errors.append(str(exc))

    schema_path = root / "config" / "schemas" / "job_hunter.schema.json"
    if schema_path.exists():
        try:
            import jsonschema

            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as exc:
            errors.append(exc.message)
        except ImportError:
            pass
    return errors


def _normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def _validate_company_entry(i: int, entry: dict[str, Any], seen_names: set[str], seen_urls: set[str]) -> list[str]:
    errors: list[str] = []
    name = str(entry.get("name") or "").strip()
    url = str(entry.get("career_url") or "").strip()
    if not name:
        errors.append(f"companies[{i}]: 'name' is required")
    if not url:
        errors.append(f"companies[{i}]: 'career_url' is required")
    elif urlsplit(url).scheme not in ("http", "https"):
        errors.append(f"companies[{i}]: 'career_url' must be http/https ({url!r})")
    if "enabled" in entry and not isinstance(entry.get("enabled"), bool):
        errors.append(f"companies[{i}]: 'enabled' must be a boolean")

    if name:
        key = name.lower()
        if key in seen_names:
            errors.append(f"companies[{i}]: duplicate company name {name!r}")
        seen_names.add(key)
    if url:
        norm = _normalize_url(url)
        if norm in seen_urls:
            errors.append(f"companies[{i}]: duplicate career_url {url!r}")
        seen_urls.add(norm)
    return errors


def validate_career_pages(data: Any) -> list[str]:
    """Structural validation for career_pages.yml's 'companies' list."""
    if not isinstance(data, dict):
        return ["career_pages.yml must be a YAML mapping"]

    companies = data.get("companies") if data.get("companies") is not None else []
    if not isinstance(companies, list):
        return ["career_pages.yml: 'companies' must be a list"]

    errors: list[str] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    for i, entry in enumerate(companies):
        if not isinstance(entry, dict):
            errors.append(f"companies[{i}]: must be a mapping")
            continue
        errors.extend(_validate_company_entry(i, entry, seen_names, seen_urls))
    return errors


def validate_career_context(text: str) -> list[str]:
    errors: list[str] = []
    if "\x00" in text:
        errors.append("career_context.md must not contain NUL bytes")
    if len(text.encode("utf-8")) > MAX_CAREER_CONTEXT_BYTES:
        errors.append(f"career_context.md exceeds max size of {MAX_CAREER_CONTEXT_BYTES} bytes")
    return errors


# ---------------------------------------------------------------------------
# Atomic write + backup
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _backup_path(root: Path, logical_name: str) -> Path:
    return root / _BACKUP_DIR_REL / f"{logical_name}.bak"


def _safe_replace(
    root: Path, logical_name: str, rel_path: Path, new_bytes: bytes, expected_revision: str
) -> dict[str, Any]:
    """Write new_bytes to rel_path iff expected_revision matches the file's current revision.

    Backs up the previous bytes (one slot per logical file) before replacing so a
    subsequent undo_last_save() can restore them.
    """
    path = root / rel_path
    current_revision = get_revision(path)
    if expected_revision != current_revision:
        return {
            "ok": False,
            "errors": ["File changed on disk since it was loaded. Reload and try again."],
            "warnings": [],
            "revision": current_revision,
        }

    previous_bytes = path.read_bytes() if path.exists() else b""
    try:
        _atomic_write(_backup_path(root, logical_name), previous_bytes)
        _atomic_write(path, new_bytes)
    except OSError as exc:
        return {
            "ok": False,
            "errors": [f"Could not save {rel_path.as_posix()}: {exc}"],
            "warnings": [],
            "revision": current_revision,
        }
    return {"ok": True, "errors": [], "warnings": [], "revision": get_revision(path)}


# ---------------------------------------------------------------------------
# job_hunter.yml
# ---------------------------------------------------------------------------


def read_job_hunter_config(root: Path) -> dict[str, Any]:
    path = root / JOB_HUNTER_CONFIG_REL
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"ok": True, "data": text, "revision": get_revision(path), "errors": [], "warnings": []}


def save_job_hunter_config(root: Path, raw_yaml_text: str, expected_revision: str) -> dict[str, Any]:
    path = root / JOB_HUNTER_CONFIG_REL
    try:
        parsed = yaml.safe_load(raw_yaml_text) or {}
    except yaml.YAMLError as exc:
        return {"ok": False, "errors": [f"Invalid YAML: {exc}"], "warnings": [], "revision": get_revision(path)}

    errors = validate_job_hunter_yaml(parsed, root)
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "revision": get_revision(path)}

    result = _safe_replace(
        root, "job_hunter_config", JOB_HUNTER_CONFIG_REL, raw_yaml_text.encode("utf-8"), expected_revision
    )
    if result["ok"]:
        get_job_hunter_config.cache_clear()
    return result


# ---------------------------------------------------------------------------
# career_pages.yml
# ---------------------------------------------------------------------------


def _extract_leading_comment(path: Path) -> str:
    """Return the file's leading run of comment/blank lines (its header block)."""
    if not path.exists():
        return ""
    leading: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        if line.strip() == "" or line.lstrip().startswith("#"):
            leading.append(line)
        else:
            break
    return "".join(leading)


def _normalize_companies(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for entry in companies:
        item: dict[str, Any] = {
            "name": str(entry.get("name") or "").strip(),
            "career_url": str(entry.get("career_url") or "").strip(),
        }
        location = entry.get("location")
        if location:
            item["location"] = str(location)
        if entry.get("enabled", True) is False:
            item["enabled"] = False
        normalized.append(item)
    return normalized


def read_career_pages(root: Path) -> dict[str, Any]:
    path = root / CAREER_PAGES_REL
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    companies = (data or {}).get("companies") or []
    return {"ok": True, "data": {"companies": companies}, "revision": get_revision(path), "errors": [], "warnings": []}


def save_career_pages(root: Path, companies: list[dict[str, Any]], expected_revision: str) -> dict[str, Any]:
    path = root / CAREER_PAGES_REL
    errors = validate_career_pages({"companies": companies})
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "revision": get_revision(path)}

    header = _extract_leading_comment(path)
    body = yaml.safe_dump({"companies": _normalize_companies(companies)}, sort_keys=False, allow_unicode=True)
    return _safe_replace(root, "career_pages", CAREER_PAGES_REL, f"{header}{body}".encode(), expected_revision)


# ---------------------------------------------------------------------------
# profile/career_context.md
# ---------------------------------------------------------------------------


def read_career_context(root: Path) -> dict[str, Any]:
    path = root / CAREER_CONTEXT_REL
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"ok": True, "data": text, "revision": get_revision(path), "errors": [], "warnings": []}


def save_career_context(root: Path, text: str, expected_revision: str) -> dict[str, Any]:
    path = root / CAREER_CONTEXT_REL
    errors = validate_career_context(text)
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "revision": get_revision(path)}
    return _safe_replace(root, "career_context", CAREER_CONTEXT_REL, text.encode("utf-8"), expected_revision)


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------


def undo_last_save(root: Path, logical_name: str) -> dict[str, Any]:
    """Restore the one backup slot kept for logical_name. Consumes the backup (one-level)."""
    rel_path = _LOGICAL_FILES.get(logical_name)
    if rel_path is None:
        return {"ok": False, "errors": [f"Unknown config file: {logical_name}"], "warnings": [], "revision": ""}

    backup = _backup_path(root, logical_name)
    if not backup.exists():
        return {"ok": False, "errors": ["No backup available to undo."], "warnings": [], "revision": ""}

    path = root / rel_path
    try:
        _atomic_write(path, backup.read_bytes())
    except OSError as exc:
        return {"ok": False, "errors": [f"Undo failed: {exc}"], "warnings": [], "revision": get_revision(path)}
    with suppress(OSError):
        backup.unlink()

    if logical_name == "job_hunter_config":
        get_job_hunter_config.cache_clear()
    return {"ok": True, "errors": [], "warnings": [], "revision": get_revision(path)}
