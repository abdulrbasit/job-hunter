from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from job_hunter.tracking.applications import (
    application_from_job,
    delete_applications_batch,
    filtered_applications,
    load_applications,
    normalize_status,
    update_application_status,
    upsert_application_from_job,
)
from job_hunter.tracking.repository import get_job_by_slug
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


def test_application_from_job_rejects_missing_score_file(tmp_path: Path) -> None:
    job_dir = tmp_path / "outputs" / "jobs" / "no-score-co"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(json.dumps({"company": "NoScoreCo", "title": "PM"}), encoding="utf-8")

    with pytest.raises(ValueError, match="no-score-co"):
        application_from_job("no-score-co", root=tmp_path)


def test_application_from_job_rejects_skip_decision(tmp_path: Path) -> None:
    job_dir = tmp_path / "outputs" / "jobs" / "skip-co"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(json.dumps({"company": "SkipCo", "title": "PM"}), encoding="utf-8")
    (job_dir / "score.yml").write_text(yaml.safe_dump({"score": 40, "decision": "SKIP"}), encoding="utf-8")

    with pytest.raises(ValueError, match="skip-co"):
        application_from_job("skip-co", root=tmp_path)


def test_application_from_job_rejects_missing_numeric_score(tmp_path: Path) -> None:
    job_dir = tmp_path / "outputs" / "jobs" / "no-number-co"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(json.dumps({"company": "NoNumberCo", "title": "PM"}), encoding="utf-8")
    (job_dir / "score.yml").write_text(yaml.safe_dump({"decision": "APPLY"}), encoding="utf-8")

    with pytest.raises(ValueError, match="no-number-co"):
        application_from_job("no-number-co", root=tmp_path)


def test_application_from_job_succeeds_for_valid_apply_score(tmp_path: Path) -> None:
    _write_job(tmp_path)

    app = application_from_job("2026-06-12_acme_pm", root=tmp_path)

    assert app["status"] == "tailored"
    assert app["score"] == 82


def test_internal_status_aliases_normalize_to_discarded() -> None:
    assert normalize_status("discarded") == "discarded"
    assert normalize_status("skip") == "discarded"


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


def test_verify_repository_accepts_language_suffixed_tailored_resume(tmp_path: Path) -> None:
    job_dir = _write_job(tmp_path, slug="2026-06-12_de_pm")
    job_dir.joinpath("resume_tailored.tex").unlink()
    job_dir.joinpath("resume_tailored.de.tex").write_text("\\documentclass{altacv}\n", encoding="utf-8")
    job_dir.joinpath("resume_tailored.de.pdf").write_bytes(b"%PDF")
    upsert_application_from_job("2026-06-12_de_pm", root=tmp_path)

    payload = verify_repository(tmp_path)

    assert not any("resume_tailored" in e for e in payload["errors"])
    assert not any("resume_tailored" in w for w in payload["warnings"])


def _set_job_url(root: Path, slug: str, url: str) -> None:
    meta_path = root / "outputs" / "jobs" / slug / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["url"] = url
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def test_delete_applications_batch_removes_db_rows_and_job_folders(tmp_path: Path) -> None:
    _write_job(tmp_path, slug="2026-06-12_acme_pm")
    _write_job(tmp_path, slug="2026-06-13_globex_pm")
    _set_job_url(tmp_path, "2026-06-13_globex_pm", "https://example.com/globex")
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)
    upsert_application_from_job("2026-06-13_globex_pm", root=tmp_path)

    result = delete_applications_batch(["2026-06-12_acme_pm", "2026-06-13_globex_pm"], root=tmp_path)

    assert result == {"deleted": 2, "skipped": [], "warnings": []}
    assert get_job_by_slug(tmp_path, "2026-06-12_acme_pm") is None
    assert get_job_by_slug(tmp_path, "2026-06-13_globex_pm") is None
    assert not (tmp_path / "outputs" / "jobs" / "2026-06-12_acme_pm").exists()
    assert not (tmp_path / "outputs" / "jobs" / "2026-06-13_globex_pm").exists()


def test_delete_applications_batch_tolerates_missing_job_folder(tmp_path: Path) -> None:
    _write_job(tmp_path, slug="2026-06-12_acme_pm")
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)
    import shutil

    shutil.rmtree(tmp_path / "outputs" / "jobs" / "2026-06-12_acme_pm")

    result = delete_applications_batch(["2026-06-12_acme_pm"], root=tmp_path)

    assert result["deleted"] == 1
    assert result["warnings"] == []


def test_delete_applications_batch_rejects_path_traversal_slug(tmp_path: Path) -> None:
    _write_job(tmp_path, slug="2026-06-12_acme_pm")
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("do not delete me", encoding="utf-8")

    result = delete_applications_batch(["../outside_secret.txt", "2026-06-12_acme_pm"], root=tmp_path)

    assert result["skipped"] == ["../outside_secret.txt"]
    assert result["deleted"] == 1
    assert outside.exists()
    assert get_job_by_slug(tmp_path, "2026-06-12_acme_pm") is None


def test_delete_applications_batch_restores_staged_folders_if_db_delete_fails(tmp_path: Path, monkeypatch) -> None:
    _write_job(tmp_path, slug="2026-06-12_acme_pm")
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)

    def boom(_root, _slugs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("job_hunter.tracking.repository.delete_jobs_by_slugs", boom)

    with pytest.raises(sqlite3.OperationalError):
        delete_applications_batch(["2026-06-12_acme_pm"], root=tmp_path)

    assert (tmp_path / "outputs" / "jobs" / "2026-06-12_acme_pm").exists()
    assert get_job_by_slug(tmp_path, "2026-06-12_acme_pm") is not None


def test_delete_application_single_delegates_to_batch(tmp_path: Path) -> None:
    from job_hunter.tracking.applications import delete_application

    _write_job(tmp_path, slug="2026-06-12_acme_pm")
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)

    delete_application("2026-06-12_acme_pm", root=tmp_path)

    assert get_job_by_slug(tmp_path, "2026-06-12_acme_pm") is None
    assert not (tmp_path / "outputs" / "jobs" / "2026-06-12_acme_pm").exists()


def test_application_from_job_output_language_from_meta(tmp_path: Path) -> None:
    job_dir = _write_job(tmp_path, slug="2026-06-12_de_pm")
    (job_dir / "resume_tailored.tex").unlink()
    (job_dir / "resume_tailored.de.tex").write_text("\\documentclass{altacv}\n", encoding="utf-8")
    meta = json.loads((job_dir / "meta.json").read_text(encoding="utf-8"))
    meta["output_language"] = "de"
    (job_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    entry = application_from_job("2026-06-12_de_pm", root=tmp_path)

    assert entry["output_language"] == "de"
    assert entry["resume_tex_path"] == "outputs/jobs/2026-06-12_de_pm/resume_tailored.de.tex"


def test_application_from_job_output_language_falls_back_to_artifact_suffix(tmp_path: Path) -> None:
    job_dir = _write_job(tmp_path, slug="2026-06-12_de_pm2")
    (job_dir / "resume_tailored.tex").unlink()
    (job_dir / "resume_tailored.de.tex").write_text("\\documentclass{altacv}\n", encoding="utf-8")

    entry = application_from_job("2026-06-12_de_pm2", root=tmp_path)

    assert entry["output_language"] == "de"


def test_application_from_job_legacy_unsuffixed_folder_has_empty_output_language(tmp_path: Path) -> None:
    _write_job(tmp_path)

    entry = application_from_job("2026-06-12_acme_pm", root=tmp_path)

    assert entry["output_language"] == ""
    assert entry["resume_tex_path"] == "outputs/jobs/2026-06-12_acme_pm/resume_tailored.tex"


def test_upsert_application_persists_output_language(tmp_path: Path) -> None:
    job_dir = _write_job(tmp_path, slug="2026-06-12_de_pm3")
    (job_dir / "resume_tailored.tex").unlink()
    (job_dir / "resume_tailored.de.tex").write_text("\\documentclass{altacv}\n", encoding="utf-8")

    upsert_application_from_job("2026-06-12_de_pm3", root=tmp_path)
    record = get_job_by_slug(tmp_path, "2026-06-12_de_pm3")

    assert record["output_language"] == "de"
