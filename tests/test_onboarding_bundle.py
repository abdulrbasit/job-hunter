"""Tests for job_hunter/config/onboarding_bundle.py — per-artifact chatbot prompts + parsing."""

from __future__ import annotations

from job_hunter.config.onboarding_bundle import (
    MAX_BUNDLE_BYTES,
    build_career_context_prompt,
    build_resume_prompt,
    build_story_bank_prompt,
    parse_single_section,
)


def _wrap(name: str, content: str) -> str:
    return f"<<<{name}>>>\n{content}\n<<<END_{name}>>>\n"


def test_career_context_prompt_includes_delimiters_and_current_text() -> None:
    prompt = build_career_context_prompt("## About Me\n- Current role:")

    assert "<<<CAREER_CONTEXT>>>" in prompt
    assert "<<<END_CAREER_CONTEXT>>>" in prompt
    assert "## About Me" in prompt


def test_story_bank_prompt_includes_delimiters_current_text_and_draft_only_rule() -> None:
    prompt = build_story_bank_prompt("## Draft\n## Final")

    assert "<<<STORY_BANK>>>" in prompt
    assert "<<<END_STORY_BANK>>>" in prompt
    assert "## Draft" in prompt
    assert "never" in prompt.lower()
    assert "Final" in prompt


def test_resume_prompt_includes_delimiters_and_all_three_inputs() -> None:
    prompt = build_resume_prompt(
        resume_tex_text="\\documentclass{altacv}",
        career_context_text="- Positioning: Product leader",
        story_bank_text="### Led a launch",
    )

    assert "<<<BASE_RESUME>>>" in prompt
    assert "<<<END_BASE_RESUME>>>" in prompt
    assert "\\documentclass{altacv}" in prompt
    assert "Positioning: Product leader" in prompt
    assert "Led a launch" in prompt


def test_parse_single_section_extracts_content() -> None:
    text = _wrap("CAREER_CONTEXT", "Targeting product management roles in Berlin.")

    content, errors = parse_single_section(text, "CAREER_CONTEXT")

    assert errors == []
    assert content == "Targeting product management roles in Berlin."


def test_parse_single_section_reports_missing_section() -> None:
    content, errors = parse_single_section("no markers here", "CAREER_CONTEXT")

    assert content is None
    assert any("CAREER_CONTEXT" in e for e in errors)


def test_parse_single_section_reports_empty_section() -> None:
    text = _wrap("STORY_BANK", "")

    content, errors = parse_single_section(text, "STORY_BANK")

    assert content is None
    assert any("empty" in e for e in errors)


def test_parse_single_section_rejects_oversized_input() -> None:
    huge = "x" * (MAX_BUNDLE_BYTES + 1)

    content, errors = parse_single_section(huge, "BASE_RESUME")

    assert content is None
    assert any("exceeds max size" in e for e in errors)


def test_parse_single_section_ignores_malformed_delimiter_order() -> None:
    text = "<<<END_CAREER_CONTEXT>>>\ncontext\n<<<CAREER_CONTEXT>>>\n"

    content, errors = parse_single_section(text, "CAREER_CONTEXT")

    assert content is None
    assert any("CAREER_CONTEXT" in e for e in errors)


def test_parse_single_section_ignores_a_different_sections_delimiters() -> None:
    text = _wrap("STORY_BANK", "story content")

    content, errors = parse_single_section(text, "CAREER_CONTEXT")

    assert content is None
    assert any("CAREER_CONTEXT" in e for e in errors)
