"""Tests for pipeline/stages/processing.py's _process_match() — artifact creation end-to-end."""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import yaml

from job_hunter.pipeline.stages import processing

_MODULE = "job_hunter.pipeline.stages.processing"
_TEX = r"\documentclass{article}\begin{document}Resume\end{document}"


def _match(company: str = "Acme", title: str = "PM", score: int = 85) -> dict:
    return {
        "score": score,
        "decision": "APPLY",
        "matched": ["Python", "SQL"],
        "matched_keywords": ["Python", "SQL"],
        "gaps": ["Kubernetes"],
        "matched_story_ids": ["STORY-01"],
        "role_summary": "Build.",
        "score_rationale": "Strong.",
        "recommendation": "Apply.",
        "job": {
            "title": title,
            "company": company,
            "url": f"https://example.com/{company.lower()}",
            "snippet": f"We need a {title} at {company}.",
            "location": "Berlin",
            "posted": "2026-06-25",
        },
    }


def test_write_match_artifacts_lives_in_dedicated_module(tmp_path: Path) -> None:
    from job_hunter.pipeline._artifacts import write_match_artifacts

    job_dir = tmp_path / "job"
    job_dir.mkdir()

    write_match_artifacts(_match(company="TestCo", score=92), job_dir, today="2026-06-25")

    meta = json.loads((job_dir / "meta.json").read_text(encoding="utf-8"))
    score = yaml.safe_load((job_dir / "score.yml").read_text(encoding="utf-8"))
    jd = (job_dir / "jd.md").read_text(encoding="utf-8")

    assert meta["company"] == "TestCo"
    assert meta["score"] == 92
    assert score["decision"] == "APPLY"
    assert "# PM @ TestCo" in jd


def _run_match(
    tmp_path: Path,
    match: dict | None = None,
    *,
    tailor_raises: bool = False,
    cover_raises: bool = False,
    pdf_raises: bool = False,
) -> bool:
    def _tailor(_m):
        if tailor_raises:
            raise RuntimeError("tailor failed")
        return _TEX

    def _cover(_m, _d):
        if cover_raises:
            raise RuntimeError("cover failed")

    def _pdf(_tex, _dir):
        if pdf_raises:
            raise RuntimeError("pdf failed")
        return str(tmp_path / "resume.pdf")

    with ExitStack() as stack:
        stack.enter_context(patch(f"{_MODULE}.JOBS_DIR", tmp_path))
        stack.enter_context(patch(f"{_MODULE}._today", return_value="2026-06-25"))
        stack.enter_context(patch(f"{_MODULE}.tailor", side_effect=_tailor))
        stack.enter_context(patch(f"{_MODULE}.write_cover", side_effect=_cover))
        stack.enter_context(patch(f"{_MODULE}.compile_tex", side_effect=_pdf))
        stack.enter_context(patch(f"{_MODULE}._write_company_research"))
        stack.enter_context(patch(f"{_MODULE}._copy_latex_assets"))
        stack.enter_context(patch(f"{_MODULE}._make_generated_tex_self_contained", side_effect=lambda t: t))
        return processing._process_match(match or _match())


def test_process_match_happy_path_returns_true(tmp_path: Path) -> None:
    assert _run_match(tmp_path) is True


def test_process_match_writes_meta_json(tmp_path: Path) -> None:
    _run_match(tmp_path, _match(company="TestCo", score=92))

    job_dir = next(tmp_path.iterdir())
    meta = json.loads((job_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["company"] == "TestCo"
    assert meta["score"] == 92
    assert meta["date"] == "2026-06-25"
    assert "url" in meta


def test_process_match_writes_score_yml(tmp_path: Path) -> None:
    _run_match(tmp_path)

    job_dir = next(tmp_path.iterdir())
    data = yaml.safe_load((job_dir / "score.yml").read_text(encoding="utf-8"))
    assert data["score"] == 85
    assert data["decision"] == "APPLY"
    assert "matched_story_ids" in data
    assert "gaps" in data


def test_process_match_writes_jd_md(tmp_path: Path) -> None:
    _run_match(tmp_path)

    job_dir = next(tmp_path.iterdir())
    assert (job_dir / "jd.md").exists()


def test_process_match_writes_resume_tex(tmp_path: Path) -> None:
    _run_match(tmp_path)

    job_dir = next(tmp_path.iterdir())
    assert (job_dir / "resume_tailored.tex").exists()


def test_process_match_tailor_failure_returns_false(tmp_path: Path) -> None:
    assert _run_match(tmp_path, tailor_raises=True) is False


def test_process_match_cover_failure_returns_false(tmp_path: Path) -> None:
    assert _run_match(tmp_path, cover_raises=True) is False


def test_process_match_pdf_failure_is_non_critical(tmp_path: Path) -> None:
    assert _run_match(tmp_path, pdf_raises=True) is True
    job_dir = next(tmp_path.iterdir())
    assert (job_dir / "resume_tailored.tex").exists()
