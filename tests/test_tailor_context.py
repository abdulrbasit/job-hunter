"""Tests for agent_context.tailor_context — agent parity with llm-api tailoring."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from job_hunter.agent_context.tailor_context import tailor_context
from job_hunter.writing.rules import (
    universal_ats_rules,
    universal_cover_letter_rules,
    universal_evidence_rules,
    universal_resume_rules,
)


def _write_score(root: Path, slug: str, data: dict) -> Path:
    path = root / "outputs" / "jobs" / slug / "score.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_tailor_context_returns_all_required_keys(tmp_path: Path) -> None:
    _write_score(tmp_path, "test-job", {"matched": ["Python", "FastAPI"], "gaps": ["Kubernetes"]})

    result = tailor_context(job="test-job", root=tmp_path)

    assert set(result) >= {
        "keywords",
        "gaps",
        "tailoring_rules",
        "positioning_rules",
        "project_rules",
        "cover_constraints",
        "writing_rules",
        "required_outputs",
    }


def test_tailor_context_keywords_and_gaps_from_score_yml(tmp_path: Path) -> None:
    _write_score(tmp_path, "slug-1", {"matched": ["Go", "gRPC"], "gaps": ["Java"]})

    result = tailor_context(job="slug-1", root=tmp_path)

    assert result["keywords"] == ["Go", "gRPC"]
    assert result["gaps"] == ["Java"]


def test_tailor_context_falls_back_to_matched_keywords_field(tmp_path: Path) -> None:
    _write_score(tmp_path, "slug-2", {"matched_keywords": ["React", "TypeScript"], "gaps": []})

    result = tailor_context(job="slug-2", root=tmp_path)

    assert result["keywords"] == ["React", "TypeScript"]


def test_tailor_context_cover_constraints_has_required_fields(tmp_path: Path) -> None:
    _write_score(tmp_path, "slug-3", {"matched": [], "gaps": []})

    cc = tailor_context(job="slug-3", root=tmp_path)["cover_constraints"]

    assert "tone" in cc
    assert isinstance(cc["target_words"], int)
    assert isinstance(cc["max_words"], int)
    assert cc["max_words"] >= cc["target_words"]
    assert isinstance(cc["paragraphs"], int)
    assert isinstance(cc["forbidden_phrases"], list)
    assert isinstance(cc["style_rules"], list)
    assert isinstance(cc["paragraph_structure"], list)
    assert len(cc["paragraph_structure"]) == cc["paragraphs"]


def test_tailor_context_cover_constraints_defaults_without_config(tmp_path: Path) -> None:
    _write_score(tmp_path, "slug-4", {"matched": [], "gaps": []})

    cc = tailor_context(job="slug-4", root=tmp_path)["cover_constraints"]

    # code-owned defaults
    assert cc["target_words"] == 220
    assert cc["max_words"] == 280
    assert cc["paragraphs"] == 4
    assert "formal" in cc["tone"]


def test_tailor_context_missing_score_yml_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="score.yml not found"):
        tailor_context(job="no-such-job", root=tmp_path)


def test_tailor_context_tailoring_rules_is_nonempty_string(tmp_path: Path) -> None:
    _write_score(tmp_path, "slug-5", {"matched": [], "gaps": []})

    result = tailor_context(job="slug-5", root=tmp_path)

    assert isinstance(result["tailoring_rules"], str)
    assert isinstance(result["positioning_rules"], str)
    assert isinstance(result["project_rules"], str)


def test_tailor_context_includes_universal_writing_rules(tmp_path: Path) -> None:
    _write_score(tmp_path, "slug-6", {"matched": [], "gaps": []})

    rules = tailor_context(job="slug-6", root=tmp_path)["writing_rules"]

    assert rules["resume"] == list(universal_resume_rules())
    assert rules["cover_letter"] == list(universal_cover_letter_rules())
    assert rules["evidence"] == list(universal_evidence_rules())
    assert rules["ats"] == list(universal_ats_rules())


def test_tailor_context_required_outputs_reference_job_slug(tmp_path: Path) -> None:
    _write_score(tmp_path, "slug-7", {"matched": [], "gaps": []})

    outputs = tailor_context(job="slug-7", root=tmp_path)["required_outputs"]
    paths = {o["path"] for o in outputs}

    # artifact filenames are always language-suffixed (base language default is "en")
    assert "outputs/jobs/slug-7/resume_tailored.en.tex" in paths
    assert "outputs/jobs/slug-7/cover_letter.en.md" in paths


def _language_fixture(tmp_path: Path, monkeypatch, *, german_base: bool) -> None:
    import json

    import job_hunter.config.loader as loader
    from job_hunter.pipeline import tailorer

    tailorer._get_base_tex.cache_clear()
    _write_score(tmp_path, "de-job", {"matched": ["Agile"], "gaps": []})
    job_dir = tmp_path / "outputs" / "jobs" / "de-job"
    (job_dir / "meta.json").write_text(
        json.dumps({"title": "Produktmanager", "company": "TestCo", "language": "de"}), encoding="utf-8"
    )
    (tmp_path / "resume.tex").write_text(r"\documentclass{article}EN", encoding="utf-8")
    resumes = {"en": {"resume_tex": "resume.tex", "base": True}}
    if german_base:
        (tmp_path / "resume_de.tex").write_text(r"\documentclass{article}DE", encoding="utf-8")
        resumes["de"] = {"resume_tex": "resume_de.tex"}
    config = {
        "profile": {"resumes": resumes},
        "filters": {"hunt_languages": ["en", "de"]},
    }
    monkeypatch.setattr(loader, "get_config", lambda name: config)
    monkeypatch.setattr(loader, "get_job_hunter_config", lambda: config)
    monkeypatch.setattr("job_hunter.config.paths.ROOT", tmp_path)


def test_tailor_context_routes_german_job_to_translate_and_tailor(tmp_path: Path, monkeypatch) -> None:
    from job_hunter.pipeline import tailorer

    _language_fixture(tmp_path, monkeypatch, german_base=False)

    result = tailor_context(job="de-job", root=tmp_path)
    tailorer._get_base_tex.cache_clear()

    language = result["language"]
    assert language["job_language"] == "de"
    assert language["output_language"] == "de"
    assert language["source_resume_language"] == "en"
    assert language["language_rules"]  # translate-and-tailor instructions present
    assert result["base_resume"] == "resume.tex"
    paths = [o["path"] for o in result["required_outputs"]]
    assert paths == ["outputs/jobs/de-job/resume_tailored.de.tex", "outputs/jobs/de-job/cover_letter.de.md"]


def test_tailor_context_uses_german_base_without_translation_rules(tmp_path: Path, monkeypatch) -> None:
    from job_hunter.pipeline import tailorer

    _language_fixture(tmp_path, monkeypatch, german_base=True)

    result = tailor_context(job="de-job", root=tmp_path)
    tailorer._get_base_tex.cache_clear()

    assert result["language"]["source_resume_language"] == "de"
    assert result["language"]["language_rules"] == []
    assert result["base_resume"] == "resume_de.tex"


def test_outreach_and_interview_contexts_carry_language_policy(tmp_path: Path, monkeypatch) -> None:
    from job_hunter.agent_context.interview_context import interview_context
    from job_hunter.agent_context.outreach_context import outreach_context
    from job_hunter.pipeline import tailorer

    _language_fixture(tmp_path, monkeypatch, german_base=False)
    (tmp_path / "outputs" / "jobs" / "de-job" / "jd.md").write_text("JD", encoding="utf-8")

    outreach = outreach_context(job="de-job", root=tmp_path)
    interview = interview_context(job="de-job", root=tmp_path)
    tailorer._get_base_tex.cache_clear()

    assert outreach["language"]["output_language"] == "de"
    assert "de" in outreach["language"]["content_policy"]
    assert interview["language"]["output_language"] == "de"
    assert "en" in interview["language"]["content_policy"]  # briefing stays in base language
