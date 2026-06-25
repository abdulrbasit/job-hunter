from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_hunter.pipeline.readme_writer import (
    TABLE_END,
    TABLE_START,
    update_readme_from_applications,
)
from job_hunter.ux.applications import (
    applications_path,
    filtered_applications,
    load_applications,
    normalize_status,
    render_applications_table,
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
    assert data["applications"][0]["notes"] == ["Applied manually"]
    assert filtered_applications(root=tmp_path, status="applied")[0]["slug"] == app["slug"]


def test_render_applications_table() -> None:
    table = render_applications_table(
        [
            {
                "date": "2026-06-12",
                "status": "tailored",
                "score": 82,
                "region": "berlin",
                "company": "Acme",
                "title": "Product Manager",
            }
        ]
    )

    assert "Status" in table
    assert "Acme - Product Manager" in table


def test_filtered_applications_backfills_empty_tracker_from_job_folders(tmp_path: Path) -> None:
    _write_job(tmp_path)

    apps = filtered_applications(root=tmp_path)

    assert len(apps) == 1
    assert apps[0]["slug"] == "2026-06-12_acme_pm"
    assert apps[0]["status"] == "tailored"
    assert applications_path(tmp_path).exists()


def test_filtered_applications_skips_low_score_backfill(tmp_path: Path) -> None:
    _write_job(tmp_path, slug="2026-06-12_low_score")
    score_path = tmp_path / "outputs" / "jobs" / "2026-06-12_low_score" / "score.yml"
    score = yaml.safe_load(score_path.read_text(encoding="utf-8"))
    score["decision"] = "SKIP"
    score_path.write_text(yaml.safe_dump(score), encoding="utf-8")

    assert filtered_applications(root=tmp_path) == []


def test_internal_status_aliases_normalize_to_rejected() -> None:
    assert normalize_status("discarded") == "rejected"
    assert normalize_status("skip") == "rejected"


def test_readme_renders_from_applications(tmp_path: Path) -> None:
    readme = f"{TABLE_START}\n| Date | Job | Location | Score | Files |\n|---|---|---|---|---|\n{TABLE_END}\n"
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    app = {
        "date": "2026-06-12",
        "slug": "2026-06-12_acme_pm",
        "company": "Acme",
        "title": "Product Manager",
        "url": "https://example.com/acme",
        "location": "Berlin",
        "score": 82,
        "status": "tailored",
    }

    update_readme_from_applications([app], tmp_path, "2026-06-12")

    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "outputs/jobs/2026-06-12_acme_pm/" in text
    assert "(tailored)" in text


def test_readme_refreshes_existing_application_score(tmp_path: Path) -> None:
    readme = (
        f"{TABLE_START}\n"
        "| Date | Job | Location | Score | Files |\n"
        "|---|---|---|---|---|\n"
        "| 2026-06-12 | [Product Manager @ Acme](https://example.com/acme) | Berlin"
        " | 0 (tailored) | [Files](outputs/jobs/2026-06-12_acme_pm/) |\n"
        f"{TABLE_END}\n"
    )
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")

    update_readme_from_applications(
        [
            {
                "date": "2026-06-12",
                "slug": "2026-06-12_acme_pm",
                "company": "Acme",
                "title": "Product Manager",
                "url": "https://example.com/acme",
                "location": "Berlin",
                "score": 82,
                "status": "tailored",
            }
        ],
        tmp_path,
        "2026-06-12",
    )

    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "| 82 (tailored) |" in text
    assert "| 0 (tailored) |" not in text


def test_verify_repository_validates_applications_and_processed_state(tmp_path: Path) -> None:
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)
    state = tmp_path / "outputs" / "state" / "discovered_urls.yml"
    state.parent.mkdir(parents=True)
    state.write_text(
        yaml.safe_dump({"discovered": ["https://example.com/acme"]}),
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "[Files](outputs/jobs/2026-06-12_acme_pm/)",
        encoding="utf-8",
    )

    payload = verify_repository(tmp_path)

    assert payload["ok"]
    assert payload["errors"] == []
