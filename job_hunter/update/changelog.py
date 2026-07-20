"""GitHub release notes for the update dialog — lazy, offline-tolerant."""

from __future__ import annotations

_RELEASES_URL = "https://api.github.com/repos/abdulrbasit/job-hunter/releases/tags/v{version}"


def github_release_notes(version: str, timeout: float = 3.0) -> str | None:
    """Return the release body for vX.Y, or None if unavailable (offline, not yet released, etc.)."""
    import requests

    try:
        response = requests.get(_RELEASES_URL.format(version=version), timeout=timeout)
        if response.status_code != 200:
            return None
        return str(response.json().get("body") or "").strip() or None
    except Exception:  # noqa: BLE001 — network/parsing failures must not crash the caller
        return None
