"""Tests for job_hunter/config/onboarding_bundle.py — any-chatbot prompt + bundle parsing."""

from __future__ import annotations

from job_hunter.config.onboarding_bundle import (
    MAX_BUNDLE_BYTES,
    build_onboarding_prompt,
    parse_onboarding_bundle,
)


def _wrap(name: str, content: str) -> str:
    return f"<<<{name}>>>\n{content}\n<<<END_{name}>>>\n"


_VALID_BUNDLE = (
    _wrap("CAREER_CONTEXT", "Targeting product management roles in Berlin.")
    + _wrap("STORY_BANK", "### Led a launch\nSituation/Task/Action/Result.")
    + _wrap("BASE_RESUME", "# Jane Doe\nProduct Manager with 5 years experience.")
)


def test_build_onboarding_prompt_includes_all_three_delimiters() -> None:
    prompt = build_onboarding_prompt({"job_titles": ["Product Manager"]})

    for name in ("CAREER_CONTEXT", "STORY_BANK", "BASE_RESUME"):
        assert f"<<<{name}>>>" in prompt
        assert f"<<<END_{name}>>>" in prompt


def test_build_onboarding_prompt_includes_configured_job_titles() -> None:
    prompt = build_onboarding_prompt({"job_titles": ["Staff Engineer"]})

    assert "Staff Engineer" in prompt


def test_parse_onboarding_bundle_extracts_all_three_sections() -> None:
    sections, errors = parse_onboarding_bundle(_VALID_BUNDLE)

    assert errors == []
    assert "Targeting product management" in sections["CAREER_CONTEXT"]
    assert "Led a launch" in sections["STORY_BANK"]
    assert "Jane Doe" in sections["BASE_RESUME"]


def test_parse_onboarding_bundle_reports_missing_section() -> None:
    bundle = _wrap("CAREER_CONTEXT", "context") + _wrap("STORY_BANK", "stories")

    sections, errors = parse_onboarding_bundle(bundle)

    assert any("BASE_RESUME" in e for e in errors)
    assert "BASE_RESUME" not in sections


def test_parse_onboarding_bundle_reports_empty_section() -> None:
    bundle = _wrap("CAREER_CONTEXT", "") + _wrap("STORY_BANK", "stories") + _wrap("BASE_RESUME", "resume")

    sections, errors = parse_onboarding_bundle(bundle)

    assert any("CAREER_CONTEXT" in e and "empty" in e for e in errors)


def test_parse_onboarding_bundle_rejects_oversized_input() -> None:
    huge = "x" * (MAX_BUNDLE_BYTES + 1)

    sections, errors = parse_onboarding_bundle(huge)

    assert sections == {}
    assert any("exceeds max size" in e for e in errors)


def test_parse_onboarding_bundle_ignores_malformed_delimiter_order() -> None:
    bundle = "<<<END_CAREER_CONTEXT>>>\ncontext\n<<<CAREER_CONTEXT>>>\n"

    sections, errors = parse_onboarding_bundle(bundle)

    assert "CAREER_CONTEXT" not in sections
    assert any("CAREER_CONTEXT" in e for e in errors)
