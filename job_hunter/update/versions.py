"""PyPI version check for job-hunter-kit: cached, offline-tolerant, never blocks startup.

cached_status() is the only call on the dashboard's hot path — it reads the on-disk
cache and does no network I/O. refresh_cache() does the actual PyPI lookup and is meant
to be run off the calling thread (see ux/web/api.py::DashAPI.get_update_status).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_PYPI_URL = "https://pypi.org/pypi/job-hunter-kit/json"
_CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_FILENAME = "update_check.json"


def installed_version() -> str:
    from job_hunter.config.loader import package_version

    return package_version()


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)) or (0,)


def is_newer(latest: str, installed: str) -> bool:
    """True if latest > installed, comparing dotted numeric parts (e.g. "0.26" > "0.25")."""
    return _version_tuple(latest) > _version_tuple(installed)


def latest_pypi_version(timeout: float = 3.0) -> str | None:
    """Query PyPI for the latest published version. Returns None on any failure — never raises."""
    import requests

    try:
        response = requests.get(_PYPI_URL, timeout=timeout)
        response.raise_for_status()
        return str(response.json()["info"]["version"])
    except Exception:  # noqa: BLE001 — network/parsing failures must not crash the caller
        return None


def _cache_path() -> Path:
    from job_hunter.launcher import platform_config_dir

    return platform_config_dir() / _CACHE_FILENAME


def _read_cache() -> dict[str, Any] | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def cached_status() -> dict[str, Any]:
    """Return the last-known update status from cache without any network call."""
    installed = installed_version()
    data = _read_cache() or {}
    latest = data.get("latest")
    return {
        "installed": installed,
        "latest": latest,
        "update_available": bool(latest) and is_newer(latest, installed),
        "checked_at": data.get("checked_at"),
    }


def cache_is_stale(checked_at: float | None = None) -> bool:
    """Whether the cache needs a refresh. Takes cached_status()'s "checked_at" — callers
    that already hold a status dict from this launch avoid a second cache-file read."""
    if checked_at is None:
        data = _read_cache()
        checked_at = data.get("checked_at") if data else None
    if not isinstance(checked_at, int | float):
        return True
    return (time.time() - checked_at) > _CACHE_TTL_SECONDS


def refresh_cache() -> dict[str, Any]:
    """Query PyPI and persist the result. Safe to call from a background thread.

    On a failed lookup (offline), the cache is left untouched rather than stamped with
    a "checked just now" timestamp — that way the next check retries immediately instead
    of waiting out the full 24h TTL while offline.
    """
    latest = latest_pypi_version()
    if latest is not None:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"latest": latest, "checked_at": time.time()}), encoding="utf-8")
    return cached_status()
