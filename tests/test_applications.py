from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_hunter.tracking.applications import (
    filtered_applications,
    load_applications,
    normalize_status,
    update_application_status,
    upsert_application_from_job,
)
from job_hunter.ux.health import verify_repository


def _write_job(root: Path, slug: str = "2026-06-12_acme_pm") -> Path:
    job_dir = root / "outputs" / "jobs" / slug
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps(
            {
                "date": "2026-06-12",
                "company": "Acme",
                "title": "Product Manager",
                "url": "https://example.com/acme",
                "region": "berlin",
                "location": "Berlin",
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "score.yml").write_text(
        yaml.safe_dump(
            {
                "score": 82,
                "decision": "APPLY",
                "role_summary": "Own a product area.",
                "score_rationale": "Strong product match.",
                "recommendation": "Apply.",
                "matched_story_ids": ["ST-01"],
                "matched": ["roadmap"],
                "gaps": [],
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "evaluation.md").write_text("# Evaluation\n", encoding="utf-8")
    (job_dir / "resume_tailored.tex").write_text("\\documentclass{altacv}\n", encoding="utf-8")
    return job_dir


def test_application_upsert_update_and_filter(tmp_path: Path) -> None:
    _write_job(tmp_path)

    app = upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)
    updated = update_application_status(
        "2026-06-12_acme_pm",
        "applied",
        root=tmp_path,
        note="Applied manually",
    )

    data = load_applications(tmp_path)
    assert app["status"] == "tailored"
    assert updated["status"] == "applied"
    assert "Applied manually" in (updated.get("notes") or [])
    assert filtered_applications(root=tmp_path, status="applied")[0]["slug"] == app["slug"]
    _ = data  # DB-backed; load_applications still returns the list


def test_update_application_status_does_not_write_readme(tmp_path: Path) -> None:
    """tracking.applications is pure state — no report generation as a side effect."""
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)

    update_application_status("2026-06-12_acme_pm", "applied", root=tmp_path)

    assert not (tmp_path / "README.md").exists()


def test_filtered_applications_after_upsert(tmp_path: Path) -> None:
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path, status="tailored")

    apps = filtered_applications(root=tmp_path)

    assert len(apps) == 1
    assert apps[0]["slug"] == "2026-06-12_acme_pm"
    assert apps[0]["status"] == "tailored"


def test_filtered_applications_skips_non_canonical_status(tmp_path: Path) -> None:
    _write_job(tmp_path, slug="2026-06-12_low_score")
    # Not upserted → no record in DB → filtered_applications returns empty
    assert filtered_applications(root=tmp_path) == []


def test_internal_status_aliases_normalize_to_rejected() -> None:
    assert normalize_status("discarded") == "rejected"
    assert normalize_status("skip") == "rejected"


def test_verify_repository_validates_applications_and_processed_state(tmp_path: Path) -> None:
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)
    (tmp_path / "README.md").write_text(
        "[Files](outputs/jobs/2026-06-12_acme_pm/)",
        encoding="utf-8",
    )

    payload = verify_repository(tmp_path)

    assert payload["ok"]
    assert payload["errors"] == []
