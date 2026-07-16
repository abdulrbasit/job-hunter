from __future__ import annotations

import re

from job_hunter.config.filter_registry import FilterRegistry


def test_registry_discovers_typed_filter_groups() -> None:
    registry = FilterRegistry.from_config(
        {
            "filters": {
                "excluded_companies": {
                    "description": "Blocked employers",
                    "entries": [
                        {"value": "Acme"},
                        {"value": "Recruiter", "note": "spam"},
                    ],
                },
                "future_filter": {"description": "Future", "entries": []},
            }
        }
    )

    assert registry.names() == ["excluded_companies", "future_filter"]
    assert registry.file("excluded_companies").entries[1].note == "spam"


def test_company_entries_choose_matching_strategy_automatically() -> None:
    registry = FilterRegistry.from_config(
        {
            "filters": {
                "excluded_companies": {
                    "description": "Blocked employers",
                    "entries": [
                        {"value": "Delivery Hero"},
                        {"value": "Auto1"},
                        {"value": r"^Spam\s+Co$"},
                        {"value": "Invalid["},
                    ],
                }
            }
        }
    )

    filters = registry.file("excluded_companies")
    assert filters.matches("Delivery Hero SE", normalize_company=True)
    assert filters.matches("AUTO1 Group", normalize_company=True)
    assert filters.matches("Spam Co", normalize_company=True)
    assert not filters.matches("Hero Digital", normalize_company=True)


def test_language_allowlist_excludes_detected_unlisted_language() -> None:
    registry = FilterRegistry.from_config(
        {
            "filters": {
                "languages": {
                    "description": "Hunt languages",
                    "entries": [{"value": "english"}],
                }
            }
        }
    )

    assert registry.allowed_languages == frozenset({"english"})


def test_matchers_are_precompiled_and_exact_values_are_frozen(monkeypatch) -> None:
    registry = FilterRegistry.from_config(
        {
            "filters": {
                "bulk": {
                    "description": "Large filter",
                    "entries": [
                        {"value": "Exact employer"},
                        {"value": "staffing agency"},
                        {"value": r"^Spam\s+Co$"},
                    ],
                }
            }
        }
    )
    filters = registry.file("bulk")
    assert isinstance(filters._exact_values, frozenset)

    def fail_compile(*args, **kwargs):
        raise AssertionError("matching must not compile regexes")

    monkeypatch.setattr(re, "compile", fail_compile)
    assert filters.matches("Exact employer")
    assert filters.matches("A staffing agency role")
    assert filters.matches("Spam Co")


def test_large_filter_set_matches_without_per_entry_scans() -> None:
    registry = FilterRegistry.from_config(
        {
            "filters": {
                "bulk": {
                    "description": "Large filter",
                    "entries": [{"value": f"blocked company {index}"} for index in range(2_000)],
                }
            }
        }
    )

    filters = registry.file("bulk")
    assert filters.matches("blocked company 1999")
    assert not filters.matches("unrelated employer and role text")


def test_capture_group_regexes_keep_independent_group_numbering() -> None:
    registry = FilterRegistry.from_config(
        {
            "filters": {
                "regexes": {
                    "description": "Advanced regexes",
                    "entries": [
                        {"value": r"(foo)\1"},
                        {"value": r"(bar)\1"},
                    ],
                }
            }
        }
    )

    filters = registry.file("regexes")
    assert filters.matches("barbar")
