"""Tests for pipeline/stages/processing.py's _write_company_research()."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from job_hunter.pipeline.stages import processing

_LLM_STAGE = "job_hunter.pipeline.llm_stage.LLMStage"


def _job(company: str = "Acme", title: str = "Product Manager") -> dict:
    return {"company": company, "title": title, "url": "https://example.com/job"}


def test_write_company_research_creates_file(tmp_path: Path) -> None:
    with (
        patch("job_hunter.pipeline.stages.processing.get_config", return_value={"job_titles": ["Product Manager"]}),
        patch(_LLM_STAGE) as mock_cls,
    ):
        mock_cls.return_value.complete.return_value = "## Product & Business\nAcme builds widgets."
        processing._write_company_research(_job(), tmp_path)

    assert (tmp_path / "company_research.md").exists()


def test_write_company_research_file_starts_with_company_header(tmp_path: Path) -> None:
    with (
        patch("job_hunter.pipeline.stages.processing.get_config", return_value={}),
        patch(_LLM_STAGE) as mock_cls,
    ):
        mock_cls.return_value.complete.return_value = "Some content."
        processing._write_company_research(_job(company="MegaCorp"), tmp_path)

    content = (tmp_path / "company_research.md").read_text(encoding="utf-8")
    assert content.startswith("# MegaCorp Research")


def test_write_company_research_includes_llm_content(tmp_path: Path) -> None:
    with (
        patch("job_hunter.pipeline.stages.processing.get_config", return_value={}),
        patch(_LLM_STAGE) as mock_cls,
    ):
        mock_cls.return_value.complete.return_value = "They build great things."
        processing._write_company_research(_job(), tmp_path)

    content = (tmp_path / "company_research.md").read_text(encoding="utf-8")
    assert "They build great things." in content


def test_write_company_research_does_not_raise_on_llm_failure(tmp_path: Path) -> None:
    with (
        patch("job_hunter.pipeline.stages.processing.get_config", return_value={}),
        patch(_LLM_STAGE) as mock_cls,
    ):
        mock_cls.return_value.complete.side_effect = RuntimeError("api error")
        processing._write_company_research(_job(), tmp_path)  # must not raise

    assert not (tmp_path / "company_research.md").exists()


def test_write_company_research_logs_warning_on_failure(tmp_path: Path, caplog) -> None:
    with (
        patch("job_hunter.pipeline.stages.processing.get_config", return_value={}),
        patch(_LLM_STAGE) as mock_cls,
        caplog.at_level(logging.WARNING),
    ):
        mock_cls.return_value.complete.side_effect = RuntimeError("timeout")
        processing._write_company_research(_job(), tmp_path)

    assert "company research failed" in caplog.text
