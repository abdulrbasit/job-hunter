"""Tests for job_hunter/writing/language.py — deterministic output-language routing."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_hunter.core.utils import find_job_artifact
from job_hunter.writing.language import (
    artifact_suffix,
    cover_language_line,
    language_name,
    resolve_output_language,
    translation_rules,
)


@pytest.mark.parametrize(
    ("job_lang", "hunt", "base", "expected"),
    [
        ("de", ["en", "de"], "en", "de"),  # detected + hunted → job language
        ("de", ["en"], "en", "en"),  # detected but not hunted → base
        (None, ["en", "de"], "en", "en"),  # undetected → base
        ("", ["en", "de"], "en", "en"),  # empty → base
        ("fr", ["en", "de", "fr"], "de", "fr"),  # any base, any target
        ("de", ["de"], "de", "de"),  # base equals target
    ],
)
def test_resolve_output_language_matrix(job_lang, hunt, base, expected) -> None:
    assert resolve_output_language(job_lang, hunt, base) == expected


def test_artifact_suffix_always_includes_language_code() -> None:
    assert artifact_suffix("de") == ".de"
    assert artifact_suffix("en") == ".en"


def test_translation_rules_name_the_target_language_and_protect_latex() -> None:
    rules = translation_rules("de")

    joined = " ".join(rules)
    assert "German" in joined
    assert "LaTeX" in joined
    assert translation_rules("") == ()


def test_cover_language_line_names_the_language() -> None:
    assert "German" in cover_language_line("de")
    assert language_name("de") == "German"
    assert language_name("xx") == "xx"  # unknown codes fall through untouched


def test_find_job_artifact_prefers_suffixed_then_legacy(tmp_path: Path) -> None:
    assert find_job_artifact(tmp_path, "resume_tailored", "tex") is None

    (tmp_path / "resume_tailored.tex").write_text("legacy", encoding="utf-8")
    assert find_job_artifact(tmp_path, "resume_tailored", "tex").name == "resume_tailored.tex"

    (tmp_path / "resume_tailored.de.tex").write_text("de", encoding="utf-8")
    assert find_job_artifact(tmp_path, "resume_tailored", "tex").name == "resume_tailored.de.tex"
