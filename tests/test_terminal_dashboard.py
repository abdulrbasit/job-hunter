from __future__ import annotations

from job_hunter.ux.terminal.dashboard import dashboard_summary, render_dashboard


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
