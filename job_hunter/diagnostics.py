"""Headless self-test for frozen desktop builds.

Verifies bundled package resources, catalogs, and core workspace operations
without opening a pywebview window — the checks a fresh install needs to get
right before a user ever sees the app. Exercised via `job-hunter internal
self-test` and the packaging smoke matrix (see docs/windows-packaging.md).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any


def _check(name: str, fn: Any) -> dict[str, Any]:
    try:
        detail = fn()
        return {"name": name, "ok": True, "detail": str(detail) if detail else ""}
    except Exception as exc:  # noqa: BLE001 — a self-test reports every failure, not just expected ones
        return {"name": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def _check_countries_resource() -> str:
    from job_hunter.config.reference_data import load_countries

    countries = load_countries()
    if len(countries) != 249:
        raise ValueError(f"expected 249 countries, got {len(countries)}")
    return f"{len(countries)} countries loaded"


def _check_filters_resource() -> str:
    from job_hunter.config.reference_data import load_filters

    filters = load_filters()
    if not filters.career_stages:
        raise ValueError("no career stages loaded")
    return f"{len(filters.career_stages)} career stages, {len(filters.languages)} languages"


def _check_catalog_resource() -> str:
    from job_hunter.catalog import load_companies

    companies = load_companies()
    if not companies:
        raise ValueError("company catalog is empty")
    return f"{len(companies)} companies loaded"


def _check_dashboard_assets() -> str:
    from importlib import resources

    web_dir = resources.files("job_hunter.ux.web")
    for name in ("dashboard.html", "dashboard.css", "dashboard.js"):
        text = web_dir.joinpath(name).read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"{name} is empty")
    return "dashboard.html/css/js present and non-empty"


def _check_workspace_and_config(tmp_root: Path) -> str:
    from job_hunter.config import service
    from job_hunter.workspace.operations import run_init

    result = run_init(tmp_root)
    read = service.read_job_hunter_config(result.workspace)
    if not read["ok"] or "mode:" not in read["data"]:
        raise ValueError("config/job_hunter.yml missing or unreadable after init")
    return f"workspace created and config readable at {result.workspace.name}"


def _check_config_save(tmp_root: Path) -> str:
    import yaml

    from job_hunter.config import service

    # A freshly-initialized workspace's job_titles is intentionally empty until
    # onboarding fills it in, which the schema (minItems: 1) rejects — patch a
    # placeholder so this checks the save path itself, not onboarding completeness.
    raw = service.read_job_hunter_config(tmp_root)
    data = yaml.safe_load(raw["data"]) or {}
    data["job_titles"] = ["Diagnostics Self-Test"]
    result = service.save_job_hunter_config(tmp_root, yaml.safe_dump(data), raw["revision"])
    if not result["ok"]:
        raise ValueError(f"config save failed: {result['errors']}")
    return "config/job_hunter.yml save round-trip ok"


def _check_db_open(tmp_root: Path) -> str:
    from job_hunter.tracking.repository import db_path, get_all_known_urls

    get_all_known_urls(tmp_root)  # opens (and migrates) the DB as a side effect
    if not db_path(tmp_root).exists():
        raise ValueError("jobs.db was not created")
    return "outputs/state/jobs.db opens and migrates cleanly"


def self_test() -> dict[str, Any]:
    """Run every headless check and return a typed pass/fail report."""
    checks = [
        _check("countries_resource", _check_countries_resource),
        _check("filters_resource", _check_filters_resource),
        _check("catalog_resource", _check_catalog_resource),
        _check("dashboard_assets", _check_dashboard_assets),
    ]
    # sqlite3.Connection's context manager only guards the transaction, not the file
    # handle (see tracking/repository.py::_conn) — on Windows an immediate rmtree can
    # race a not-yet-garbage-collected connection, so this cleans up best-effort
    # rather than via TemporaryDirectory's strict (exception-raising) teardown.
    tmp = tempfile.mkdtemp(prefix="job-hunter-self-test-")
    try:
        tmp_root = Path(tmp) / "workspace"
        checks.append(_check("workspace_and_config", lambda: _check_workspace_and_config(tmp_root)))
        checks.append(_check("config_save", lambda: _check_config_save(tmp_root)))
        checks.append(_check("db_open", lambda: _check_db_open(tmp_root)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
