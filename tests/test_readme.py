"""Tests for pipeline/stages/readme.py — README.md table generation."""

from __future__ import annotations

from pathlib import Path

from job_hunter.pipeline.stages.readme import (
    TABLE_END,
    TABLE_START,
    update_readme_from_applications,
)


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


def test_readme_update_only_writes_the_readme_file(tmp_path: Path) -> None:
    """No hidden state mutation — this is an output/report generator, nothing else."""
    readme = f"{TABLE_START}\n| Date | Job | Location | Score | Files |\n|---|---|---|---|---|\n{TABLE_END}\n"
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}

    update_readme_from_applications(
        [{"date": "2026-06-12", "slug": "s", "company": "Acme", "title": "PM", "url": "https://x", "score": 1}],
        tmp_path,
        "2026-06-12",
    )

    after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before
