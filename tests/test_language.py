from __future__ import annotations

import time

from job_hunter.core.language import detect_language


def test_german_description_detected() -> None:
    result = detect_language("PM", "Wir suchen einen erfahrenen Produktmanager fuer unser Team in Berlin.")

    assert result.code == "de"


def test_english_description_detected() -> None:
    result = detect_language("Product Manager", "We are looking for an experienced product manager to join our team.")

    assert result.code == "en"


def test_mixed_title_and_description_prefers_description() -> None:
    result = detect_language("Product Manager", "Wir suchen einen erfahrenen Produktmanager fuer unser Team in Berlin.")

    assert result.code == "de"


def test_empty_description_falls_back_to_title() -> None:
    result = detect_language("Wir suchen einen erfahrenen Produktmanager", "")

    assert result.code == "de"


def test_ambiguous_short_text_fails_open() -> None:
    result = detect_language("Manager", "")

    assert result.code is None


def test_empty_input_fails_open() -> None:
    result = detect_language("", "")

    assert result.code is None
    assert result.confidence == 0.0


def test_detects_one_thousand_postings_within_time_budget() -> None:
    detect_language("warmup", "warmup text to build the detector")

    start = time.perf_counter()
    for _ in range(1000):
        detect_language(
            "Product Manager",
            "We are looking for an experienced product manager to join our growing team in Berlin.",
        )
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0
