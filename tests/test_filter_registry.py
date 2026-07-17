from __future__ import annotations

import re

from job_hunter.filters import FILTER_TYPES, FilterSet, canonicalize_filter_config
from job_hunter.models import FilterMatchMode


def test_package_registry_defines_known_filter_types_and_modes() -> None:
    assert set(FILTER_TYPES) == {
        "excluded_companies",
        "excluded_titles",
        "excluded_industries",
        "hunt_languages",
        "experience_levels",
    }
    assert FILTER_TYPES["excluded_companies"].mode == FilterMatchMode.CONTAINS
    assert FILTER_TYPES["excluded_titles"].mode == FilterMatchMode.CONTAINS
    assert FILTER_TYPES["excluded_industries"].mode == FilterMatchMode.CONTAINS
    assert FILTER_TYPES["hunt_languages"].mode == FilterMatchMode.EXACT
    assert FILTER_TYPES["experience_levels"].mode == FilterMatchMode.EXACT


def test_scalar_choices_bind_to_package_matching_logic() -> None:
    filters = FilterSet.from_config(
        {
            "filters": {
                "excluded_companies": ["Delivery Hero", "Auto1"],
                "excluded_titles": ["intern"],
                "excluded_industries": ["aerospace_defense"],
                "hunt_languages": ["en", "de"],
            }
        }
    )

    assert filters.matches("excluded_companies", "Delivery Hero SE")
    assert filters.matches("excluded_companies", "AUTO1 Group")
    assert not filters.matches("excluded_companies", "Hero Digital")
    assert filters.matches("excluded_titles", "Product Management Intern")
    assert filters.matches("excluded_industries", "Defense aviation systems")
    assert filters.values("hunt_languages") == ["en", "de"]


def test_legacy_nested_groups_canonicalize_in_memory_without_mutating_input() -> None:
    config = {
        "filters": {
            "languages": {"description": "Allowed", "entries": [{"value": "english"}]},
            "excluded_companies": {
                "description": "Blocked",
                "entries": [{"value": "Acme", "note": "spam"}],
            },
        }
    }

    canonical = canonicalize_filter_config(config)

    assert canonical["filters"] == {
        "excluded_companies": ["Acme"],
        "hunt_languages": ["en"],
    }
    assert isinstance(config["filters"]["excluded_companies"], dict)


def test_matchers_do_not_compile_during_matching(monkeypatch) -> None:
    filters = FilterSet.from_config({"filters": {"excluded_companies": ["Acme"], "excluded_titles": ["intern"]}})

    def fail_compile(*args, **kwargs):
        raise AssertionError("matching must not compile regexes")

    monkeypatch.setattr(re, "compile", fail_compile)
    assert filters.matches("excluded_companies", "Acme GmbH")
    assert filters.matches("excluded_titles", "Product Intern")


def test_unknown_filter_types_are_not_discovered_from_user_config() -> None:
    filters = FilterSet.from_config({"filters": {"future_filter": ["value"]}})

    assert filters.names() == []


def test_identical_choices_reuse_compiled_matchers() -> None:
    config = {"filters": {"excluded_titles": ["intern"], "hunt_languages": ["en"]}}

    first = FilterSet.from_config(config)
    second = FilterSet.from_config(config)

    assert first.bound["excluded_titles"] is second.bound["excluded_titles"]
    assert first.bound["hunt_languages"] is second.bound["hunt_languages"]
    assert first.bound["hunt_languages"]._contains is None
