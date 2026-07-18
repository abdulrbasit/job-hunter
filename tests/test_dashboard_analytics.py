from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from job_hunter.tracking.applications import upsert_application
from job_hunter.ux.analytics import analyze_pipeline


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


def test_analyze_pipeline_reports_funnel_exclusions_and_response_rate(tmp_path: Path) -> None:
    from job_hunter.tracking.repository import insert_jobs, mark_candidates_discarded

    insert_jobs(
        tmp_path,
        [
            {"url": "https://example.com/1", "title": "PM", "company": "Acme"},
            {"url": "https://example.com/2", "title": "PM", "company": "Acme"},
            {"url": "https://example.com/3", "title": "PM", "company": "Acme"},
        ],
    )
    mark_candidates_discarded(tmp_path, [{"url": "https://example.com/1", "reason": "wrong_location"}])
    upsert_application({"slug": "applied", "status": "applied", "score": 82, "url": "https://x/a"}, root=tmp_path)
    upsert_application({"slug": "responded", "status": "responded", "score": 70, "url": "https://x/b"}, root=tmp_path)

    report = analyze_pipeline(tmp_path)

    assert report["funnel"]["found"] == 5  # 3 candidates + 2 applications
    assert report["funnel"]["screened"] == 4  # minus the 1 discarded
    assert report["funnel"]["applied"] == 2
    assert report["exclusion_reasons"] == {"wrong_location": 1}
    assert report["response_rate"] == 0.5  # 1 of 2 applied reached responded+
