"""Tests for agent_context.interview_context — bounded job/story data for interview prep."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_hunter.agent_context.interview_context import interview_context
from job_hunter.writing.rules import universal_evidence_rules


def _write_job(root: Path, slug: str, *, meta: dict, jd: str, score: dict) -> None:
    folder = root / "outputs" / "jobs" / slug
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (folder / "jd.md").write_text(jd, encoding="utf-8")
    (folder / "score.yml").write_text(yaml.safe_dump(score), encoding="utf-8")


def test_interview_context_returns_all_required_keys(tmp_path: Path) -> None:
    _write_job(
        tmp_path,
        "slug-1",
        meta={"company": "ExampleCo", "title": "PM"},
        jd="We need kubernetes and terraform infrastructure expertise.",
        score={"matched_story_ids": ["FN-01"]},
    )

    result = interview_context(job="slug-1", root=tmp_path)

    assert set(result) >= {"job", "matched_stories", "writing_rules", "required_outputs"}


def test_interview_context_includes_job_meta_and_score(tmp_path: Path) -> None:
    _write_job(
        tmp_path,
        "slug-2",
        meta={"company": "ExampleCo", "title": "PM"},
        jd="short jd",
        score={"matched_story_ids": ["FN-01"]},
    )

    result = interview_context(job="slug-2", root=tmp_path)

    assert result["job"]["meta"]["company"] == "ExampleCo"
    assert result["job"]["score"]["matched_story_ids"] == ["FN-01"]


def test_interview_context_matched_stories_ranks_by_jd_overlap(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"profile": {"story_bank": "profile/story_bank.md"}}), encoding="utf-8"
    )
    story_bank = tmp_path / "profile" / "story_bank.md"
    story_bank.parent.mkdir(parents=True)
    story_bank.write_text(
        """# Role One

## Final -- refined STAR stories

### FN-01 - Kubernetes migration
**Rating: 9/10**
Situation: led a kubernetes and terraform infrastructure migration.
- **Tags:** kubernetes, terraform, infrastructure
""",
        encoding="utf-8",
    )
    _write_job(
        tmp_path,
        "slug-3",
        meta={},
        jd="We need kubernetes and terraform infrastructure expertise.",
        score={},
    )

    result = interview_context(job="slug-3", root=tmp_path)

    assert result["matched_stories"][0]["id"] == "FN-01"


def test_interview_context_writing_rules_use_universal_evidence_rules(tmp_path: Path) -> None:
    _write_job(tmp_path, "slug-4", meta={}, jd="", score={})

    result = interview_context(job="slug-4", root=tmp_path)

    assert result["writing_rules"]["evidence"] == list(universal_evidence_rules())


def test_interview_context_required_outputs_reference_job_slug(tmp_path: Path) -> None:
    _write_job(tmp_path, "slug-5", meta={}, jd="", score={})

    outputs = interview_context(job="slug-5", root=tmp_path)["required_outputs"]

    assert any(o["path"] == "outputs/jobs/slug-5/interview_prep.md" for o in outputs)
