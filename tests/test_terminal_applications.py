from __future__ import annotations

from job_hunter.ux.terminal.applications import render_applications_table


def test_render_applications_table() -> None:
    table = render_applications_table(
        [
            {
                "discovered_at": "2026-06-12",
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
