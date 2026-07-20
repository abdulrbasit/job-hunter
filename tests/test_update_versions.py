"""Tests for job_hunter/update/versions.py — PyPI version check, cache, offline tolerance."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from job_hunter.update import versions


@pytest.fixture(autouse=True)
def _isolated_platform_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))


@pytest.mark.parametrize(
    ("latest", "installed", "expected"),
    [
        ("0.26", "0.25", True),
        ("0.25", "0.25", False),
        ("0.24", "0.25", False),
        ("1.0", "0.99", True),
        ("v0.26", "0.25", True),  # non-numeric prefix ignored
        ("unknown", "0.25", False),  # no digits at all -> (0,) <= anything real
    ],
)
def test_is_newer(latest: str, installed: str, expected: bool) -> None:
    assert versions.is_newer(latest, installed) is expected


def test_latest_pypi_version_returns_none_on_request_failure() -> None:
    with patch("requests.get", side_effect=RuntimeError("offline")):
        assert versions.latest_pypi_version() is None


def test_latest_pypi_version_returns_none_on_bad_status() -> None:
    response = MagicMock()
    response.raise_for_status.side_effect = RuntimeError("500")
    with patch("requests.get", return_value=response):
        assert versions.latest_pypi_version() is None


def test_latest_pypi_version_parses_info_version() -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"info": {"version": "0.26"}}
    with patch("requests.get", return_value=response) as mock_get:
        assert versions.latest_pypi_version() == "0.26"
        assert mock_get.call_args.kwargs["timeout"] == 3.0


def test_cached_status_with_no_cache_file() -> None:
    with patch("job_hunter.config.loader.package_version", return_value="0.25"):
        status = versions.cached_status()
    assert status == {"installed": "0.25", "latest": None, "update_available": False, "checked_at": None}


def test_cache_is_stale_true_with_no_cache_file() -> None:
    assert versions.cache_is_stale() is True


def test_cache_is_stale_accepts_a_checked_at_directly_without_reading_the_cache_file() -> None:
    """DashAPI.get_update_status() passes cached_status()'s own "checked_at" here so a
    single dashboard-startup call reads the cache file once, not twice."""
    import time

    assert versions.cache_is_stale(time.time()) is False
    assert versions.cache_is_stale(time.time() - versions._CACHE_TTL_SECONDS - 1) is True
    assert versions.cache_is_stale(None) is True
    assert versions.cache_is_stale("not-a-number") is True


def test_refresh_cache_writes_and_cached_status_reflects_it() -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"info": {"version": "0.26"}}
    with (
        patch("requests.get", return_value=response),
        patch("job_hunter.config.loader.package_version", return_value="0.25"),
    ):
        result = versions.refresh_cache()
        assert result["latest"] == "0.26"
        assert result["update_available"] is True
        assert versions.cache_is_stale() is False

        status = versions.cached_status()
    assert status["update_available"] is True
    assert status["latest"] == "0.26"


def test_refresh_cache_offline_leaves_cache_untouched_and_stays_stale() -> None:
    with patch("requests.get", side_effect=RuntimeError("offline")):
        result = versions.refresh_cache()
    assert result["latest"] is None
    assert versions.cache_is_stale() is True  # retry next time, not after a 24h wait
