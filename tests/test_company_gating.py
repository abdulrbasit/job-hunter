"""Tests for job_hunter/companies/gating.py — region + industry gating for company hunts."""

from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.companies import gating


def test_enabled_countries_collects_countries_from_enabled_regions() -> None:
    config = {
        "regions": {
            "a": {"enabled": True, "country": "DE", "scope": "country"},
            "b": {"enabled": False, "country": "FR", "scope": "country"},
        }
    }

    assert gating.enabled_countries(config) == ["DE"]


def test_enabled_countries_empty_when_no_regions() -> None:
    assert gating.enabled_countries({"regions": {}}) == []


def test_enabled_countries_none_when_remote_global_enabled() -> None:
    config = {"regions": {"a": {"enabled": True, "scope": "remote_global"}}}

    assert gating.enabled_countries(config) is None


def test_excluded_industry_ids_matches_by_label_and_alias() -> None:
    assert gating.excluded_industry_ids(["Software & IT", "fintech"]) == {"software_it", "finance"}


def test_excluded_industry_ids_unknown_term_matches_nothing() -> None:
    assert gating.excluded_industry_ids(["not-a-real-industry"]) == set()


def _write_config(root: Path, data: dict) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "job_hunter.yml").write_text(yaml.safe_dump(data), encoding="utf-8")


def test_hunt_candidates_returns_only_companies_in_enabled_regions(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        {
            "companies": {
                "targets": [
                    {"name": "Acme DE", "url": "https://acme.example/de", "country": "DE"},
                    {"name": "Acme US", "url": "https://acme.example/us", "country": "US"},
                ]
            }
        },
    )
    config = {"regions": {"primary": {"enabled": True, "country": "DE", "scope": "country"}}}

    result = gating.hunt_candidates(tmp_path, config)

    assert [c["name"] for c in result] == ["Acme DE"]
    assert result[0]["career_url"] == "https://acme.example/de"
    assert result[0]["location"] == "DE"


def test_hunt_candidates_respects_excluded_industries(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        {
            "companies": {
                "targets": [
                    {"name": "Acme", "url": "https://acme.example/de", "country": "DE", "industry": "software_it"}
                ]
            }
        },
    )
    config = {
        "regions": {"primary": {"enabled": True, "country": "DE", "scope": "country"}},
        "filters": {"excluded_industries": ["software_it"]},
    }

    assert gating.hunt_candidates(tmp_path, config) == []


def test_hunt_candidates_empty_when_no_targets_and_no_enabled_catalog_companies(tmp_path: Path) -> None:
    _write_config(tmp_path, {})
    config = {"regions": {"primary": {"enabled": True, "country": "DE", "scope": "country"}}}

    assert gating.hunt_candidates(tmp_path, config) == []
