"""Tests for job_hunter/diagnostics.py — headless self-test for frozen builds."""

from __future__ import annotations

from job_hunter.diagnostics import self_test


def test_self_test_reports_ok_true_when_everything_passes() -> None:
    payload = self_test()

    assert payload["ok"] is True
    assert len(payload["checks"]) == 7


def test_self_test_covers_every_named_check() -> None:
    payload = self_test()

    names = {c["name"] for c in payload["checks"]}
    assert names == {
        "countries_resource",
        "filters_resource",
        "catalog_resource",
        "dashboard_assets",
        "workspace_and_config",
        "config_save",
        "db_open",
    }


def test_self_test_all_checks_individually_pass() -> None:
    payload = self_test()

    for check in payload["checks"]:
        assert check["ok"] is True, f"{check['name']} failed: {check['detail']}"


def test_self_test_reports_ok_false_and_error_detail_on_failure(monkeypatch) -> None:
    def boom():
        raise RuntimeError("resource missing")

    monkeypatch.setattr("job_hunter.diagnostics._check_countries_resource", boom)

    payload = self_test()

    assert payload["ok"] is False
    failed = next(c for c in payload["checks"] if c["name"] == "countries_resource")
    assert failed["ok"] is False
    assert "resource missing" in failed["detail"]
