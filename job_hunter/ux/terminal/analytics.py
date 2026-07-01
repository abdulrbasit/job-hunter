"""Text rendering of the pipeline analytics report for the terminal."""

from __future__ import annotations

from typing import Any


def render_analytics(report: dict[str, Any]) -> str:
    lines = ["Job Hunter Analytics", f"Total applications: {report['total']}"]
    lines.append(_render_counter("Status", report["by_status"]))
    lines.append(_render_counter("Region", report["by_region"]))
    lines.append(_render_counter("Sources", report["source_quality"]))
    lines.append(f"Low-score themes: {len(report['low_score_reasons'])}")
    for item in report["low_score_reasons"][:8]:
        lines.append(f"- {item['slug']}: {item['score']} ({', '.join(item['gaps']) or 'no gaps'})")
    lines.append(f"Stale active postings: {len(report['stale_postings'])}")
    for item in report["stale_postings"][:8]:
        lines.append(f"- {item['slug']}: {item['status']} since {item['updated_at']}")
    lines.append(f"Follow-up candidates: {len(report['followups'])}")
    for item in report["followups"][:8]:
        lines.append(f"- {item['slug']}: {item['status']} since {item['updated_at']}")
    return "\n".join(lines)


def _render_counter(label: str, counts: dict[str, int]) -> str:
    if not counts:
        return f"{label}: none"
    return f"{label}: " + ", ".join(f"{key}={value}" for key, value in counts.items())
