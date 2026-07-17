"""Tests for job_hunter/config/reference_data.py — countries.json, filters.json, experience-level resolution."""

from __future__ import annotations

from job_hunter.config.reference_data import (
    country_codes,
    experience_level,
    experience_level_names,
    load_countries,
    resolve_experience_range,
    resolve_max_years_experience,
    resolve_title_exclusions,
)

# ---------------------------------------------------------------------------
# Catalog loading — Phase 1 gate: all 249 countries load
# ---------------------------------------------------------------------------


def test_all_249_countries_load() -> None:
    countries = load_countries()

    assert len(countries) == 249


def test_country_codes_are_unique_two_letter_codes() -> None:
    countries = load_countries()
    codes = [c.code for c in countries]

    assert len(codes) == len(set(codes))
    assert all(len(code) == 2 and code.isupper() for code in codes)


def test_known_countries_present_with_reviewed_languages() -> None:
    codes = country_codes()

    assert "DE" in codes
    assert "US" in codes
    assert "JP" in codes
    germany = next(c for c in load_countries() if c.code == "DE")
    assert "de" in germany.reviewed_languages


def test_filters_expose_sixteen_experience_levels() -> None:
    assert len(experience_level_names()) == 16
    assert "senior" in experience_level_names()
    assert "student_intern" in experience_level_names()


# ---------------------------------------------------------------------------
# resolve_title_exclusions — user's own excluded_titles only
# ---------------------------------------------------------------------------


def test_resolve_title_exclusions_returns_user_terms_only() -> None:
    config = {"filters": {"excluded_titles": ["marketing", "sales"]}}

    assert resolve_title_exclusions(config) == ["marketing", "sales"]


def test_resolve_title_exclusions_empty_when_unset() -> None:
    assert resolve_title_exclusions({}) == []


# ---------------------------------------------------------------------------
# resolve_experience_range / resolve_max_years_experience
# ---------------------------------------------------------------------------


def test_resolve_experience_range_unions_selected_levels() -> None:
    config = {"filters": {"experience_levels": ["associate", "mid", "senior"]}}

    assert resolve_experience_range(config) == (1, 9)


def test_resolve_experience_range_uncapped_when_any_level_is_uncapped() -> None:
    config = {"filters": {"experience_levels": ["senior", "principal"]}}

    assert resolve_experience_range(config) == (5, None)


def test_resolve_experience_range_defaults_to_all_levels_when_unset() -> None:
    min_years, max_years = resolve_experience_range({})

    assert min_years == 0
    assert max_years is None


def test_resolve_max_years_experience_derives_from_selected_levels() -> None:
    config = {"filters": {"experience_levels": ["entry", "junior"]}}

    assert resolve_max_years_experience(config) == 2


def test_resolve_max_years_experience_uncapped_returns_sentinel() -> None:
    config = {"filters": {"experience_levels": ["director"]}}

    assert resolve_max_years_experience(config) == 999


def test_explicit_max_years_override_wins_over_experience_levels() -> None:
    config = {"filters": {"experience_levels": ["entry", "junior"]}, "scoring": {"max_years_experience_required": 12}}

    assert resolve_max_years_experience(config) == 12


def test_experience_level_unknown_id_returns_none() -> None:
    assert experience_level("not-a-real-level") is None


def test_experience_level_known_id_returns_level() -> None:
    level = experience_level("senior")

    assert level is not None
    assert level.min_years == 5
    assert level.max_years == 9
