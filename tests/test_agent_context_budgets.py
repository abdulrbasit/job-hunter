"""Per-context byte-budget guards: asserts every agent-facing payload stays under a fixed
serialized-JSON size, built against intentionally oversized fixtures (long JD, long career
context/resume, several stories). Complements test_agent_context.py's per-field clip
assertions with an overall payload ceiling — the actual thing that bounds a batch run's
token spend.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_hunter.agent_context.evidence_context import evidence_context
from job_hunter.agent_context.interview_context import interview_context
from job_hunter.agent_context.outreach_context import outreach_context
from job_hunter.agent_context.score_context import profile_context, score_context
from job_hunter.agent_context.tailor_context import tailor_context

_LONG_JD = "Requirement. " * 2000  # ~26KB raw, must clip down to MAX_JD_CHARS
_LONG_CAREER_CONTEXT = "About me. Targeting. Resume style. " * 500  # ~18KB raw
_LONG_RESUME = "\\documentclass{altacv}\n" + ("Experience bullet. " * 1000)  # ~20KB raw

_STORY_BANK = "\n\n".join(
    f"""# Role {i}

## Final -- refined STAR stories

### ST-{i:02d} - Story {i}
**Rating: 8/10**
Situation: {"Detailed verified situation text. " * 20}
- **Tags:** product
"""
    for i in range(1, 6)
)


def _write_workspace(root: Path, *, jd: str = _LONG_JD) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump(
            {
                "scoring": {"min_fit_score": 70},
                "job_titles": ["Product Manager"],
                "filters": {},
                "profile": {
                    "resume_tex": "profile/resume_double_column.tex",
                    "story_bank": "profile/story_bank.md",
                    "career_context": "profile/career_context.md",
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "profile").mkdir(exist_ok=True)
    (root / "profile" / "career_context.md").write_text(_LONG_CAREER_CONTEXT, encoding="utf-8")
    (root / "profile" / "resume_double_column.tex").write_text(_LONG_RESUME, encoding="utf-8")
    (root / "profile" / "story_bank.md").write_text(_STORY_BANK, encoding="utf-8")

    job_dir = root / "outputs" / "jobs" / "job-slug"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps({"company": "ExampleCo", "title": "Product Manager"}), encoding="utf-8"
    )
    (job_dir / "jd.md").write_text(jd, encoding="utf-8")
    (job_dir / "score.yml").write_text(yaml.safe_dump({"status": "pending"}), encoding="utf-8")


def _size(payload: dict) -> int:
    return len(json.dumps(payload))


def test_score_context_full_with_profile_stays_under_budget(tmp_path: Path) -> None:
    _write_workspace(tmp_path)

    payload = score_context(mode="full", root=tmp_path, job="job-slug")

    assert _size(payload) < 16_000


def test_score_context_full_without_profile_stays_under_budget(tmp_path: Path) -> None:
    """The batch case: profile fetched once elsewhere, omitted per job."""
    _write_workspace(tmp_path)

    payload = score_context(mode="full", root=tmp_path, job="job-slug", include_profile=False)

    assert _size(payload) < 10_000
    assert isinstance(payload["profile"], str)  # sentinel, not the embedded profile block


def test_score_context_snippet_stays_under_budget(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        json.dumps({"jobs": [{"title": "PM", "company": "ExampleCo", "snippet": "short " * 200}]}),
        encoding="utf-8",
    )

    payload = score_context(mode="snippet", root=tmp_path, queue=queue_path)

    assert _size(payload) < 10_000


def test_profile_context_stays_under_budget(tmp_path: Path) -> None:
    _write_workspace(tmp_path)

    payload = profile_context(tmp_path)

    assert _size(payload) < 9_000


def test_interview_context_stays_under_budget(tmp_path: Path) -> None:
    _write_workspace(tmp_path)

    payload = interview_context(job="job-slug", root=tmp_path)

    assert _size(payload) < 6_000


def test_outreach_context_stays_under_budget(tmp_path: Path) -> None:
    _write_workspace(tmp_path)

    payload = outreach_context(job="job-slug", root=tmp_path)

    assert _size(payload) < 6_000


def test_evidence_context_is_tiny() -> None:
    assert _size(evidence_context()) < 1_000


def test_tailor_context_stays_under_budget(tmp_path: Path) -> None:
    (tmp_path / "outputs" / "jobs" / "job-slug").mkdir(parents=True)
    (tmp_path / "outputs" / "jobs" / "job-slug" / "score.yml").write_text(
        yaml.safe_dump({"matched": ["Python"] * 20, "gaps": ["Kubernetes"] * 10}), encoding="utf-8"
    )

    payload = tailor_context(job="job-slug", root=tmp_path)

    assert _size(payload) < 6_000
