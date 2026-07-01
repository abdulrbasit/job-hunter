"""Text rendering of application records for the terminal."""

from __future__ import annotations

from typing import Any


def render_applications_table(apps: list[dict[str, Any]]) -> str:
    rows = ["#   Date       Status      Score  Region       Company - Role"]
    rows.append("-" * 82)
    for i, app in enumerate(apps, 1):
        score = app.get("score")
        score_text = "" if score in (None, "") else str(score)
        role = f"{app.get('company', 'Unknown')} - {app.get('title', 'Unknown')}"
        rows.append(
            f"{i:<3} "
            f"{str(app.get('discovered_at') or app.get('created_at') or '')[:10]:<10} "
            f"{str(app.get('status') or ''):<11} "
            f"{score_text:<6} "
            f"{str(app.get('region') or app.get('location') or '')[:12]:<12} "
            f"{role}"
        )
    return "\n".join(rows)
