"""Tests for agent_context.outreach_context — bounded job/story data when scoped to a job."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_hunter.agent_context.outreach_context import outreach_context


def _write_job(root: Path, slug: str, *, meta: dict, jd: str, score: dict) -> None:
    folder = root / "outputs" / "jobs" / slug
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (folder / "jd.md").write_text(jd, encoding="utf-8")
    (folder / "score.yml").write_text(yaml.safe_dump(score), encoding="utf-8")


def test_outreach_context_without_job_is_rules_only(tmp_path: Path) -> None:
    result = outreach_context(root=tmp_path)

    assert set(result) == {"writing_rules"}


def test_outreach_context_with_job_adds_job_and_matched_stories(tmp_path: Path) -> None:
    _write_job(
        tmp_path,
        "slug-1",
        meta={"company": "ExampleCo", "title": "PM"},
        jd="short jd",
        score={"matched_story_ids": ["FN-01"]},
    )

    result = outreach_context(job="slug-1", root=tmp_path)

    assert set(result) >= {"writing_rules", "job", "matched_stories", "required_outputs"}
    assert result["job"]["meta"]["company"] == "ExampleCo"


def test_outreach_context_required_outputs_reference_job_slug(tmp_path: Path) -> None:
    _write_job(tmp_path, "slug-2", meta={}, jd="", score={})

    outputs = outreach_context(job="slug-2", root=tmp_path)["required_outputs"]

    assert any(o["path"] == "outputs/jobs/slug-2/outreach_drafts.md" for o in outputs)
