from __future__ import annotations

from job_hunter.config.filter_registry import FilterRegistry


def test_registry_discovers_typed_filter_groups() -> None:
    registry = FilterRegistry.from_config(
        {
            "filters": {
                "excluded_companies": {
                    "description": "Blocked employers",
                    "entries": [
                        {"value": "Acme"},
                        {"value": "Recruiter", "match": "contains", "note": "spam"},
                    ],
                },
                "future_filter": {"description": "Future", "entries": []},
            }
        }
    )

    assert registry.names() == ["excluded_companies", "future_filter"]
    assert registry.file("excluded_companies").entries[1].note == "spam"
    assert registry.file("excluded_companies").entries[0].match is None


def test_company_entries_match_automatically_or_by_explicit_mode() -> None:
    registry = FilterRegistry.from_config(
        {
            "filters": {
                "excluded_companies": {
                    "description": "Blocked employers",
                    "entries": [
                        {"value": "Delivery Hero"},
                        {"value": "Auto1"},
                        {"value": r"^Spam\s+Co$", "match": "regex"},
                        {"value": "Invalid[", "match": "regex"},
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
