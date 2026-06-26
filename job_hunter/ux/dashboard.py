"""Terminal dashboard rendering and lightweight interactive controls."""

from __future__ import annotations

import sys
from datetime import date
from typing import Any

from job_hunter.pipeline.readme_writer import update_readme_from_applications
from job_hunter.ux.applications import ApplicationRecord, render_applications_table, update_application_status


def dashboard_summary(apps: list[ApplicationRecord]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for app in apps:
        status = str(app.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {"total": len(apps), "by_status": dict(sorted(counts.items()))}


def render_dashboard(apps: list[ApplicationRecord]) -> str:
    summary = dashboard_summary(apps)
    lines = ["Job Hunter Dashboard"]
    lines.append(f"Total: {summary['total']}")
    if summary["by_status"]:
        status_bits = [f"{status}={count}" for status, count in summary["by_status"].items()]
        lines.append("Status: " + ", ".join(status_bits))
    lines.append("")
    lines.append(render_applications_table(apps))
    return "\n".join(lines)


def run_interactive_dashboard(apps: list[dict[str, Any]], root) -> int:
    """Run a small stdlib dashboard loop for terminals."""
    if not sys.stdin.isatty():
        print(render_dashboard(apps))
        return 0

    current_apps = list(apps)
    while True:
        print(render_dashboard(current_apps))
        print("")
        print("Commands: number=preview, u <number> <status>=update, q=quit")
        command = input("dashboard> ").strip()
        if command.lower() in {"q", "quit", "exit"}:
            return 0
        if command.isdigit():
            idx = int(command) - 1
            if 0 <= idx < len(current_apps):
                _print_preview(current_apps[idx])
            continue
        parts = command.split()
        if len(parts) >= 3 and parts[0].lower() in {"u", "update"} and parts[1].isdigit():
            idx = int(parts[1]) - 1
            if 0 <= idx < len(current_apps):
                status = parts[2]
                note = " ".join(parts[3:])
                app = update_application_status(
                    str(current_apps[idx].get("slug") or ""),
                    status,
                    root=root,
                    note=note,
                )
                current_apps[idx] = app
                print(f"Updated {app['slug']} -> {app['status']}")
                update_readme_from_applications(current_apps, root, date.today().isoformat())


def _print_preview(app: ApplicationRecord) -> None:
    print("")
    print(f"{app.get('company', 'Unknown')} - {app.get('title', 'Unknown')}")
    print(f"Status: {app.get('status', '')} | Score: {app.get('score', '')}")
    print(f"URL: {app.get('url', '')}")
    files = app.get("files") if isinstance(app.get("files"), dict) else {}
    for label, path in files.items():
        if path:
            print(f"{label}: {path}")
    notes = app.get("notes") or []
    if notes:
        print("Notes: " + " | ".join(str(note) for note in notes[-3:]))
    print("")
