"""Terminal dashboard rendering and lightweight interactive controls."""

from __future__ import annotations

import sys
from datetime import date
from typing import Any

from job_hunter.tracking.applications import (
    CANONICAL_STATUSES,
    ApplicationRecord,
    delete_application,
    update_application_status,
)
from job_hunter.ux.terminal.applications import render_applications_table

_HELP = (
    "Statuses: tailored | applied | responded | interview | offer | rejected\n"
    "Commands:  <num>                     preview job\n"
    "           u <num> <status> [note]   update status\n"
    "           d <num>                   delete job (removes files)\n"
    "           q                         quit"
)


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


def _refresh_readme(root) -> None:
    from job_hunter.pipeline.stages.readme import update_readme_from_applications
    from job_hunter.tracking.applications import load_applications

    apps = load_applications(root)["applications"]
    update_readme_from_applications(apps, root, date.today().isoformat())


def run_interactive_dashboard(apps: list[dict[str, Any]], root) -> int:
    """Run a small stdlib dashboard loop for terminals."""
    if not sys.stdin.isatty():
        print(render_dashboard(apps))
        return 0

    current_apps = list(apps)
    print(_HELP)
    while True:
        print(render_dashboard(current_apps))
        print("")
        command = input("dashboard> ").strip()
        if not command:
            continue
        if command.lower() in {"q", "quit", "exit"}:
            return 0

        parts = command.split()

        # Preview: <num>
        if len(parts) == 1 and parts[0].isdigit():
            num = int(parts[0])
            if 1 <= num <= len(current_apps):
                _print_preview(current_apps[num - 1])
            else:
                print(f"No job #{num}. Range: 1-{len(current_apps)}")
            continue

        # Update: u <num> <status> [note]
        if len(parts) >= 3 and parts[0].lower() in {"u", "update"} and parts[1].isdigit():
            num = int(parts[1])
            if not (1 <= num <= len(current_apps)):
                print(f"No job #{num}. Range: 1-{len(current_apps)}")
                continue
            raw_status = parts[2]
            note = " ".join(parts[3:])
            try:
                app = update_application_status(
                    str(current_apps[num - 1].get("slug") or ""),
                    raw_status,
                    root=root,
                    note=note,
                )
            except ValueError as exc:
                print(str(exc))
                print(f"Valid statuses: {', '.join(CANONICAL_STATUSES)}")
                continue
            except KeyError as exc:
                print(f"Application not found: {exc}")
                continue
            _refresh_readme(root)
            current_apps[num - 1] = app
            print(f"Updated {app['slug']} -> {app['status']}")
            continue

        # Delete: d <num>
        if len(parts) == 2 and parts[0].lower() == "d" and parts[1].isdigit():
            num = int(parts[1])
            if not (1 <= num <= len(current_apps)):
                print(f"No job #{num}. Range: 1-{len(current_apps)}")
                continue
            slug = str(current_apps[num - 1].get("slug") or "")
            print(f"Warning: permanently deletes {slug} from tracker and outputs/jobs/{slug}/.")
            confirm = input("Type 'yes' to confirm: ").strip().lower()
            if confirm == "yes":
                delete_application(slug, root)
                _refresh_readme(root)
                current_apps.pop(num - 1)
                print(f"Deleted {slug}.")
            else:
                print("Cancelled.")
            continue

        print(f"Unknown command.\n{_HELP}")


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
