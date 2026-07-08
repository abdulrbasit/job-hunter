"""Tests for job_hunter/config/reference_data.py — countries.json, filters.json, career_stage resolution."""

from __future__ import annotations

from job_hunter.config.reference_data import (
    career_stage,
    career_stage_names,
    country_codes,
    load_countries,
    load_filters,
    preferred_title_terms,
    resolve_max_years_experience,
    resolve_title_exclusions,
)
from job_hunter.core.utils import has_excluded_title_term

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


def test_filters_expose_all_five_career_stages() -> None:
    assert set(career_stage_names()) == {"student", "early_career", "experienced", "leadership", "custom"}


def test_filters_expose_sixteen_reviewed_languages() -> None:
    languages = load_filters().languages
    reviewed = [name for name, lang in languages.items() if lang.review_status == "reviewed"]

    assert len(reviewed) == 16
    assert "german" in reviewed
    assert "english" in reviewed


# ---------------------------------------------------------------------------
# career_stage backward compatibility (custom / missing key)
# ---------------------------------------------------------------------------


def test_missing_career_stage_key_resolves_to_custom_and_preserves_user_terms() -> None:
    config = {"exclusions": {"title_terms": ["marketing"]}}

    assert resolve_title_exclusions(config) == ["marketing"]


def test_custom_career_stage_disables_system_exclusions() -> None:
    config = {"career_stage": "custom", "exclusions": {"title_terms": ["sales"]}}

    assert resolve_title_exclusions(config) == ["sales"]


def test_custom_career_stage_preserves_legacy_max_years_fallback() -> None:
    config = {"career_stage": "custom", "scoring": {}}

    assert resolve_max_years_experience(config) == 4


def test_missing_scoring_section_preserves_legacy_fallback() -> None:
    assert resolve_max_years_experience({}) == 4


# ---------------------------------------------------------------------------
# Hard-filter exclusions per stage
# ---------------------------------------------------------------------------


def test_student_stage_excludes_senior_titles() -> None:
    excluded = resolve_title_exclusions({"career_stage": "student", "exclusions": {"title_terms": []}})

    assert has_excluded_title_term("Senior Product Manager", excluded)
    assert not has_excluded_title_term("Junior Product Manager", excluded)


def test_experienced_stage_excludes_internship_and_junior_titles() -> None:
    excluded = resolve_title_exclusions({"career_stage": "experienced", "exclusions": {}})

    assert has_excluded_title_term("Marketing Internship", excluded)
    assert has_excluded_title_term("Junior Analyst", excluded)
    assert not has_excluded_title_term("Senior Analyst", excluded)


def test_leadership_stage_excludes_early_career_titles() -> None:
    excluded = resolve_title_exclusions({"career_stage": "leadership", "exclusions": {}})

    assert has_excluded_title_term("Graduate Software Engineer", excluded)
    assert not has_excluded_title_term("Director of Engineering", excluded)


def test_user_title_terms_are_additive_with_stage_excludes() -> None:
    excluded = resolve_title_exclusions({"career_stage": "student", "exclusions": {"title_terms": ["sales"]}})

    assert "sales" in excluded
    assert "senior" in excluded


def test_stage_and_user_excludes_are_deduped() -> None:
    excluded = resolve_title_exclusions({"career_stage": "student", "exclusions": {"title_terms": ["senior"]}})

    assert excluded.count("senior") == 1


# ---------------------------------------------------------------------------
# Word-boundary false-positive protection (existing has_excluded_title_term)
# ---------------------------------------------------------------------------


def test_student_exclude_does_not_match_substring_false_positive() -> None:
    excluded = resolve_title_exclusions({"career_stage": "student", "exclusions": {}})

    # "lead" is excluded for students, but must not match "Team Leadgen" or "Leader" style substrings.
    assert not has_excluded_title_term("Leadgen Specialist Intern", excluded)


def test_experienced_exclude_does_not_match_partial_word() -> None:
    excluded = resolve_title_exclusions({"career_stage": "experienced", "exclusions": {}})

    # "intern" is excluded, but must not match "International" as a substring.
    assert not has_excluded_title_term("International Sales Manager", excluded)


# ---------------------------------------------------------------------------
# Default experience caps
# ---------------------------------------------------------------------------


def test_student_default_max_years_is_one() -> None:
    assert resolve_max_years_experience({"career_stage": "student"}) == 1


def test_early_career_default_max_years_is_three() -> None:
    assert resolve_max_years_experience({"career_stage": "early_career"}) == 3


def test_experienced_default_max_years_is_eight() -> None:
    assert resolve_max_years_experience({"career_stage": "experienced"}) == 8


def test_leadership_has_no_years_cap() -> None:
    assert resolve_max_years_experience({"career_stage": "leadership"}) >= 999


def test_explicit_max_years_override_wins_over_career_stage() -> None:
    config = {"career_stage": "student", "scoring": {"max_years_experience_required": 12}}

    assert resolve_max_years_experience(config) == 12


# ---------------------------------------------------------------------------
# Positive ranking (preferred signals — soft, never mandatory)
# ---------------------------------------------------------------------------


def test_student_preferred_terms_include_internship_signals() -> None:
    prefer = preferred_title_terms({"career_stage": "student"})

    assert "internship" in prefer
    assert "working student" in prefer


def test_leadership_preferred_terms_include_director_signals() -> None:
    prefer = preferred_title_terms({"career_stage": "leadership"})

    assert "director" in prefer


def test_custom_stage_has_no_preferred_terms() -> None:
    assert preferred_title_terms({"career_stage": "custom"}) == []


def test_career_stage_unknown_name_falls_back_to_custom() -> None:
    stage = career_stage("not-a-real-stage")

    assert stage.exclude == []
    assert stage.prefer == []
