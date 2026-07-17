from __future__ import annotations

import time

from job_hunter.core.experience import detect_experience


def test_english_plus_years_pattern() -> None:
    result = detect_experience("Senior Engineer", "Requires 5+ years of experience in backend systems.")

    assert result.confident
    assert result.min_years == 5
    assert result.max_years is None


def test_english_spelled_out_minimum() -> None:
    result = detect_experience("Engineer", "Candidates must have at least three years of experience.")

    assert result.confident
    assert result.min_years == 3
    assert result.max_years is None


def test_german_range_pattern() -> None:
    result = detect_experience("Ingenieur", "Sie bringen 3-5 Jahre Berufserfahrung mit.")

    assert result.confident
    assert result.min_years == 3
    assert result.max_years == 5


def test_german_mindestens_pattern() -> None:
    result = detect_experience("PM", "Wir suchen jemanden mit mind. 5 Jahren Berufserfahrung.", hunt_language="de")

    assert result.confident
    assert result.min_years == 5
    assert result.max_years is None


def test_german_compound_adjective_pattern() -> None:
    result = detect_experience("PM", "Erforderlich ist eine dreijährige Berufserfahrung.", hunt_language="de")

    assert result.confident
    assert result.min_years == 3
    assert result.max_years is None


def test_bare_years_reads_as_open_lower_bound() -> None:
    result = detect_experience("Engineer", "5 years of experience in distributed systems required.")

    assert result.confident
    assert result.min_years == 5
    assert result.max_years is None


def test_werkstudent_keyword_detected() -> None:
    result = detect_experience("Werkstudent Marketing", "", hunt_language="de")

    assert result.confident
    assert result.level_id == "student_working_student"
    assert result.min_years == 0
    assert result.max_years == 0


def test_praktikum_keyword_detected() -> None:
    result = detect_experience("Praktikum Softwareentwicklung", "", hunt_language="de")

    assert result.confident
    assert result.level_id == "student_intern"


def test_abschlussarbeit_keyword_detected() -> None:
    result = detect_experience("Abschlussarbeit im Bereich KI", "", hunt_language="de")

    assert result.confident
    assert result.level_id == "student_thesis"


def test_senior_keyword_detected() -> None:
    result = detect_experience("Senior Backend Engineer", "")

    assert result.confident
    assert result.level_id == "senior"
    assert result.min_years == 5
    assert result.max_years == 9


def test_principal_keyword_detected() -> None:
    result = detect_experience("Principal Engineer", "")

    assert result.confident
    assert result.level_id == "principal"
    assert result.min_years == 10
    assert result.max_years is None


def test_english_seniority_keyword_leaks_into_unsupported_language() -> None:
    result = detect_experience("Senior Engineer", "", hunt_language="fr")

    assert result.confident
    assert result.level_id == "senior"


def test_product_manager_title_does_not_false_positive_as_manager_level() -> None:
    """Regression: bare 'manager' matched inside 'Product Manager' — a common IC-track
    title, not a people-management role — wrongly resolving to the 5-10y manager level."""
    result = detect_experience("Product Manager", "Join our mission-driven team and help shape the roadmap.")

    assert not result.confident


def test_lead_generation_title_does_not_false_positive_as_lead_level() -> None:
    """Regression: bare 'lead' matched inside 'Lead Generation Specialist' — a sales/
    marketing title unrelated to seniority — wrongly resolving to the 7-12y lead level."""
    result = detect_experience("Lead Generation Specialist", "Generate qualified sales leads for our team.")

    assert not result.confident


def test_engineering_manager_keyword_detected() -> None:
    result = detect_experience("Engineering Manager", "Lead a team of 8 engineers.")

    assert result.confident
    assert result.level_id == "manager"


def test_tech_lead_keyword_detected() -> None:
    result = detect_experience("Tech Lead", "")

    assert result.confident
    assert result.level_id == "lead"


def test_ambiguous_text_fails_open() -> None:
    result = detect_experience("Software Engineer", "Join our growing team and make an impact.")

    assert not result.confident
    assert result.min_years is None
    assert result.max_years is None


def test_empty_input_fails_open() -> None:
    result = detect_experience("", "")

    assert not result.confident


def test_detects_one_thousand_postings_within_time_budget() -> None:
    detect_experience("warmup", "warmup text with 3 years of experience")

    start = time.perf_counter()
    for _ in range(1000):
        detect_experience(
            "Senior Backend Engineer",
            "We require 5+ years of experience building distributed systems in Python.",
        )
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0
