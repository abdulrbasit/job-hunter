from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from job_hunter.ux.analytics import analyze_pipeline
from job_hunter.ux.applications import upsert_application
from job_hunter.ux.dashboard import dashboard_summary, render_dashboard


def test_dashboard_summary_and_render() -> None:
    apps = [
        {"status": "tailored", "company": "Acme", "title": "PM", "date": "2026-06-12"},
        {"status": "applied", "company": "Beta", "title": "PO", "date": "2026-06-11"},
    ]

    summary = dashboard_summary(apps)
    text = render_dashboard(apps)

    assert summary == {"total": 2, "by_status": {"applied": 1, "tailored": 1}}
    assert "Job Hunter Dashboard" in text
    assert "Total: 2" in text
    assert "Acme - PM" in text


def test_analyze_pipeline_reports_counts_and_followups(tmp_path: Path) -> None:
    old = (datetime.now(UTC) - timedelta(days=10)).replace(microsecond=0).isoformat()
    upsert_application(
        {
            "slug": "low",
            "status": "tailored",
            "score": 55,
            "region": "berlin",
            "url": "https://jobs.example.com/low",
            "updated_at": old,
        },
        root=tmp_path,
    )
    upsert_application(
        {
            "slug": "applied",
            "status": "applied",
            "score": 82,
            "region": "remote",
            "url": "https://boards.greenhouse.io/acme",
            "updated_at": old,
        },
        root=tmp_path,
    )
    score_dir = tmp_path / "outputs" / "jobs" / "low"
    score_dir.mkdir(parents=True)
    (score_dir / "score.yml").write_text(
        yaml.safe_dump({"gaps": ["No payments domain evidence", "Seniority stretch"]}),
        encoding="utf-8",
    )

    report = analyze_pipeline(tmp_path, days=7)

    assert report["total"] == 2
    assert report["by_status"] == {"applied": 1, "tailored": 1}
    assert report["by_region"] == {"berlin": 1, "remote": 1}
    assert report["source_quality"]["jobs.example.com"] == 1
    assert report["low_score_reasons"][0]["slug"] == "low"
    assert report["followups"][0]["slug"] == "applied"
    assert any(item["slug"] == "low" for item in report["stale_postings"])
