"""Generate the local morning briefing artifact."""

from __future__ import annotations

from datetime import date

from job_hunter.agent_context import build_candidate_queue
from job_hunter.tracker import repo_path, today_path, write_artifact
from job_hunter.ux.applications import active_application_count


def _candidate_section() -> str:
    candidate_dir = repo_path("outputs", "candidates")
    if not candidate_dir.exists():
        return "No candidate snapshots yet - run: `job-hunter run-daily --region primary`"

    queue = build_candidate_queue(root=repo_path(), scope="briefing-backlog", limit=10000)
    reports = queue.get("source_reports", [])
    if not reports:
        return "No candidate snapshots yet - run: `job-hunter run-daily --region primary`"

    lines: list[str] = []
    hidden_processed = 0
    hidden_empty = 0
    for report in reports:
        queued = int(report.get("queued") or 0)
        total = int(report.get("total_seen") or 0)
        reason = str(report.get("reason") or "")
        if queued:
            status = f"{queued}/{total} unprocessed"
            lines.append(f"- `{report.get('file', '')}` - {status}")
        elif reason == "no_candidates":
            hidden_empty += 1
        else:
            hidden_processed += 1

    lines.append("")
    if queue["count"]:
        lines.append(
            f"**{queue['count']} unprocessed candidate(s) across {len(lines) - 1} active file(s).** "
            "Run `/job-hunter batch` to score and tailor."
        )
        if hidden_processed or hidden_empty:
            hidden_parts = []
            if hidden_processed:
                hidden_parts.append(f"{hidden_processed} processed/duplicate file(s)")
            if hidden_empty:
                hidden_parts.append(f"{hidden_empty} empty file(s)")
            lines.append(f"Hidden from brief: {', '.join(hidden_parts)}.")
    else:
        lines.append("All candidates processed. Run `job-hunter run-daily` to scrape new ones.")

    return "\n".join(lines)


def build_briefing() -> str:
    return f"""# Morning Briefing - {date.today().isoformat()}

## Candidates
{_candidate_section()}

## Applications
- Active applications: {active_application_count(repo_path())}
- Review dashboard: `job-hunter dashboard --no-interactive`

## Today's Focus
- Run `/job-hunter batch` to score and tailor backlog candidates.
- Run `/job-hunter one <url>` to process a single job manually.
- Keep every external action human-reviewed - never submit automatically.
"""


def write_today_briefing() -> object:
    return write_artifact(today_path("briefings"), build_briefing())
