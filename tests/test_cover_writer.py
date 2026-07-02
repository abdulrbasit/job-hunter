"""Tests for pipeline/cover_writer.py — LLM calls are mocked."""

import os
from unittest.mock import MagicMock, patch

import pytest

from job_hunter.pipeline import cover_writer
from job_hunter.writing.rules import universal_cover_letter_rules

CONFIG = {
    "header": {
        "include_date": False,
        "hiring_manager": "Hiring Manager",
        "salutation": "Dear Hiring Manager,",
    },
    "closing": {"format": "Best regards,\nCandidate Name"},
}

MATCH = {
    "job": {
        "title": "Product Manager",
        "company": "TestCo",
        "url": "https://testco.com/job",
        "snippet": "PM role at TestCo.",
        "posted_date_text": "2026-04-01",
    },
    "score": 85,
}

BODY = (
    "I bring strong PM experience to this role. "
    "My work at ExampleCo demonstrates cross-functional leadership. "
    "TestCo's platform approach is compelling. "
    "Happy to discuss further."
)


def test_write_cover_creates_markdown(tmp_path, mock_llm_client) -> None:
    with patch("job_hunter.pipeline.cover_writer.get_llm_client", return_value=mock_llm_client(BODY)):
        md_path = cover_writer.write_cover(MATCH, str(tmp_path), CONFIG)

    assert os.path.exists(md_path)


def test_write_cover_markdown_contains_company(tmp_path, mock_llm_client) -> None:
    with patch("job_hunter.pipeline.cover_writer.get_llm_client", return_value=mock_llm_client(BODY)):
        md_path = cover_writer.write_cover(MATCH, str(tmp_path), CONFIG)

    content = open(md_path, encoding="utf-8").read()
    assert "TestCo" in content
    assert "Best regards" in content


def test_write_cover_returns_md_path(tmp_path, mock_llm_client) -> None:
    with patch("job_hunter.pipeline.cover_writer.get_llm_client", return_value=mock_llm_client(BODY)):
        md_path = cover_writer.write_cover(MATCH, str(tmp_path), CONFIG)

    assert md_path.endswith("cover_letter.md")
    assert os.path.exists(md_path)


def test_write_cover_api_error_raises(tmp_path) -> None:
    mock = MagicMock()
    mock.complete.side_effect = Exception("API down")
    with patch("job_hunter.pipeline.cover_writer.get_llm_client", return_value=mock):
        with pytest.raises(Exception, match="API down"):
            cover_writer.write_cover(MATCH, str(tmp_path), CONFIG)


def test_write_cover_no_forbidden_phrases(tmp_path, mock_llm_client) -> None:
    forbidden = [
        "I am passionate",
        "I am excited to apply",
        "Thank you for your time",
        "I look forward to hearing from you",
        "Kind regards",
    ]
    with patch("job_hunter.pipeline.cover_writer.get_llm_client", return_value=mock_llm_client(BODY)):
        md_path = cover_writer.write_cover(MATCH, str(tmp_path), CONFIG)

    content = open(md_path, encoding="utf-8").read().lower()
    for phrase in forbidden:
        assert phrase.lower() not in content, f"Forbidden phrase found: {phrase}"


def test_write_cover_no_story_id_citations(tmp_path, mock_llm_client) -> None:
    body_with_citation = BODY + " Core platform components [STORY-01] drive adoption."
    with patch(
        "job_hunter.pipeline.cover_writer.get_llm_client",
        return_value=mock_llm_client(body_with_citation),
    ):
        md_path = cover_writer.write_cover(MATCH, str(tmp_path), CONFIG)

    content = open(md_path, encoding="utf-8").read()
    # Story ID citations are forbidden — if the LLM ignored the instruction,
    # this test surfaces it so the prompt can be tightened.
    import re

    assert not re.search(r"\[[A-Z]+-\d+\]", content), "Story ID citation found in cover letter"


def test_cover_writer_system_prompt_includes_universal_rules() -> None:
    system = cover_writer._build_system(CONFIG.get("cover_letter", {}), "candidate background", 6000)
    for rule in universal_cover_letter_rules():
        assert rule in system


def test_cover_writer_system_prompt_keeps_universal_rules_despite_config() -> None:
    """cover_letter config (user-editable) cannot remove the evidence/citation rules."""
    permissive_config = {"forbidden": {"style": [], "phrases": []}}
    system = cover_writer._build_system(permissive_config, "candidate background", 6000)
    for rule in universal_cover_letter_rules():
        assert rule in system
