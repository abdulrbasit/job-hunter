"""Tests for agent_context.tailor_context — agent parity with llm-api tailoring."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from job_hunter.agent_context.tailor_context import tailor_context


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
