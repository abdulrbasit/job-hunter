from __future__ import annotations

import warnings
from pathlib import Path

import pytest
import yaml

from job_hunter.catalog.loader import CompanyEntry
from job_hunter.catalog.merge import company_matches_enabled_locations
from job_hunter.config.loader import get_job_hunter_config_for_root
from job_hunter.config.locations import (
    canonicalize_runtime_location,
    enabled_locations,
    legacy_location_warnings,
    location_matches_any,
    resolve_config_location,
)
from job_hunter.models import JobPosting, Location, LocationScope
from job_hunter.pipeline.stages.screening import screen_jobs_by_rules
from job_hunter.sources import orchestrator
from job_hunter.ux.web.api import DashAPI


def _city_region(country: str, city_id: str) -> dict:
    return {
        "enabled": True,
        "country": country,
        "scope": "city",
        "city_id": city_id,
    }


def test_config_resolution_canonicalizes_munich_aliases() -> None:
    english = resolve_config_location("DE", "Munich", LocationScope.CITY)
    german = resolve_config_location("DE", "München", LocationScope.CITY)

    assert english.city is not None
    assert german.city is not None
    assert english.city.id == german.city.id == "geonames:2867714"
    assert english.city.name == "Munich"


def test_config_resolution_reports_deterministic_fuzzy_suggestions() -> None:
    with pytest.raises(ValueError, match="suggestions:"):
        resolve_config_location("DE", "Berln", LocationScope.CITY)


def test_runtime_resolution_is_exact_not_fuzzy() -> None:
    assert canonicalize_runtime_location("München, Germany")
    assert canonicalize_runtime_location("Munchin, Germany") == []


def test_munich_and_berlin_scopes_do_not_match_stuttgart() -> None:
    config = {
        "regions": {
            "munich": _city_region("DE", "geonames:2867714"),
            "berlin": _city_region("DE", "geonames:2950159"),
        }
    }
    allowed = enabled_locations(config)

    assert location_matches_any(canonicalize_runtime_location("Berlin, Germany"), allowed)
    assert location_matches_any(canonicalize_runtime_location("Munich, Germany"), allowed)
    assert not location_matches_any(canonicalize_runtime_location("Stuttgart, Germany"), allowed)


def test_country_and_remote_scope_semantics() -> None:
    country = resolve_config_location("DE", scope=LocationScope.COUNTRY)
    remote_country = canonicalize_runtime_location("Remote - Germany")
    global_remote = canonicalize_runtime_location("Remote")

    assert location_matches_any(remote_country, [country])
    assert not location_matches_any(global_remote, [country])
    assert location_matches_any(
        remote_country,
        [resolve_config_location("DE", scope=LocationScope.REMOTE_COUNTRY)],
    )
    assert location_matches_any(
        global_remote,
        [resolve_config_location("", scope=LocationScope.REMOTE_GLOBAL)],
    )


def test_screening_fails_closed_for_disabled_city_and_unknown_location() -> None:
    config = {
        "job_titles": ["Product Manager"],
        "regions": {
            "munich": _city_region("DE", "geonames:2867714"),
            "berlin": _city_region("DE", "geonames:2950159"),
        },
    }
    jobs = [
        {"title": "Product Manager", "company": "A", "url": "https://a.example/job", "location": "Berlin"},
        {
            "title": "Product Manager",
            "company": "B",
            "url": "https://b.example/job",
            "location": "Stuttgart",
        },
        {"title": "Product Manager", "company": "C", "url": "https://c.example/job", "location": ""},
    ]

    kept, rejected = screen_jobs_by_rules(jobs, config)

    assert [job["company"] for job in kept] == ["A"]
    assert {job["company"] for job in rejected} == {"B", "C"}
    assert {job["_rejection_reason"] for job in rejected} == {"location_not_enabled"}


def test_legacy_region_is_canonicalized_in_memory_and_warns(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "job_hunter.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "regions": {
                    "berlin": {"enabled": True, "country": "DE", "location": "Berlin"},
                }
            }
        ),
        encoding="utf-8",
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = get_job_hunter_config_for_root(tmp_path)

    assert loaded["regions"]["berlin"]["city_id"] == "geonames:2950159"
    assert any("legacy free-text" in str(item.message) for item in caught)
    assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8"))["regions"]["berlin"]["location"], str)


def test_doctor_location_warning_only_reports_legacy_regions() -> None:
    canonical = _city_region("DE", "geonames:2950159")
    assert legacy_location_warnings({"regions": {"berlin": canonical}}) == []
    assert (
        "legacy free-text"
        in legacy_location_warnings({"regions": {"berlin": {"country": "DE", "location": "Berlin"}}})[0]
    )
    assert (
        "cannot resolve"
        in legacy_location_warnings(
            {"regions": {"unknown": {"country": "DE", "scope": "city", "city_id": "geonames:missing"}}}
        )[0]
    )


def test_doctor_flags_workspace_owned_location_dataset(tmp_path: Path, monkeypatch) -> None:
    from job_hunter.ux import health

    config = tmp_path / "config"
    (config / "locations").mkdir(parents=True)
    (config / "job_hunter.yml").write_text("mode: agent\n", encoding="utf-8")
    monkeypatch.setattr(health, "is_chromium_installed", lambda: True)

    check = next(item for item in health.doctor(tmp_path)["checks"] if item["name"] == "package_owned_locations")

    assert check["ok"] is False


def test_dashboard_serves_all_countries_and_only_requested_country_cities(tmp_path: Path) -> None:
    api = DashAPI(tmp_path)

    countries_payload = api.get_location_countries()
    cities_payload = api.get_location_cities("DE")

    assert len(countries_payload["countries"]) == 249
    assert cities_payload["country"] == "DE"
    assert any(city["id"] == "geonames:2950159" for city in cities_payload["cities"])
    assert all(set(city) == {"id", "name"} for city in cities_payload["cities"])


def test_dashboard_detects_legacy_region_as_active_package_city(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "job_hunter.yml").write_text(
        yaml.safe_dump({"regions": {"berlin": {"enabled": True, "country": "DE", "location": "Berlin"}}}),
        encoding="utf-8",
    )

    form = DashAPI(tmp_path).get_job_hunter_config_form()["data"]["form"]

    assert form["regions"]["berlin"]["scope"] == "city"
    assert form["regions"]["berlin"]["city_id"] == "geonames:2950159"


def test_orchestrator_rejects_disabled_city_and_skips_unsupported_country_source(monkeypatch) -> None:
    config = {
        "job_titles": ["Product Manager"],
        "regions": {"berlin": _city_region("DE", "geonames:2950159")},
    }
    calls: list[tuple[str, Location | None]] = []

    class GermanySource:
        source_name = "germany"
        global_feed = False

        def supports_country(self, country: str) -> bool:
            return country == "DE"

        def fetch(self, params):
            calls.append(("germany", params.canonical_location))
            return [
                JobPosting(title="Product Manager", company="A", url="https://example.com/jobs/a", location="Berlin"),
                JobPosting(
                    title="Product Manager", company="B", url="https://example.com/jobs/b", location="Stuttgart"
                ),
            ]

    class UnitedStatesSource:
        source_name = "us-only"
        global_feed = False

        def supports_country(self, country: str) -> bool:
            return country == "US"

        def fetch(self, params):
            calls.append(("us-only", params.canonical_location))
            return []

    monkeypatch.setattr(orchestrator, "load_search_config", lambda: config)
    monkeypatch.setattr(orchestrator, "board_adapters", lambda: [GermanySource(), UnitedStatesSource()])
    monkeypatch.setattr(orchestrator, "probe_search_providers", lambda: set())
    monkeypatch.setattr(orchestrator, "load_cached_candidate_urls", lambda: set())

    jobs, stats = orchestrator.scrape_with_stats(depth="fast")

    assert calls[0][0] == "germany"
    assert calls[0][1] is not None
    assert calls[0][1].id == "city:DE:geonames:2950159"
    assert [job.company for job in jobs] == ["A"]
    assert stats.rejected["location_not_enabled"] == 1


def test_company_hunt_candidate_requires_enabled_city_metadata() -> None:
    allowed = enabled_locations(
        {
            "regions": {
                "munich": _city_region("DE", "geonames:2867714"),
                "berlin": _city_region("DE", "geonames:2950159"),
            }
        }
    )

    def company(city: str) -> CompanyEntry:
        return CompanyEntry(
            id=city.lower(),
            name=city,
            career_url=f"https://{city.lower()}.example/careers",
            country_codes=["DE"],
            city_tags=[city],
            industry_ids=["software_it"],
            verified_at="2026-07-16",
        )

    assert company_matches_enabled_locations(company("Berlin"), allowed)
    assert not company_matches_enabled_locations(company("Stuttgart"), allowed)
