"""Resolve which config/job_hunter.yml region a scheduled hunt slot should run."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

from job_hunter.config.loader import ROOT, get_config

DEFAULT_CONFIG_PATH = ROOT / "config" / "job_hunter.yml"


def enabled_regions(config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    regions = config.get("regions") or {}
    return [(name, region) for name, region in regions.items() if region.get("enabled", True)]


def hunt_schedules(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def resolve_hunt_region(
    config: dict[str, Any],
    event_name: str,
    event_schedule: str,
    input_region: str,
    configured_schedules: list[str],
) -> tuple[int, dict[str, str]]:
    regions = enabled_regions(config)
    region_names = [name for name, _ in regions]
    primary_regions = [name for name, region in regions if region.get("primary", False)]
    primary_region = primary_regions[0] if primary_regions else (region_names[0] if region_names else "")
    secondary_regions = [name for name in region_names if name != primary_region]

    requested = (input_region or "").strip()

    if event_name == "schedule":
        if event_schedule not in configured_schedules:
            return 0, {
                "should_run": "false",
                "reason": f"Schedule {event_schedule!r} is not a configured hunt slot",
            }

        slot = configured_schedules.index(event_schedule)
        if slot == 0:
            if not primary_region:
                return 0, {
                    "should_run": "false",
                    "reason": "No enabled region configured for the primary slot",
                }
            region = primary_region
        else:
            secondary_idx = slot - 1
            if secondary_idx >= len(secondary_regions):
                return 0, {
                    "should_run": "false",
                    "reason": (f"No secondary region configured for hunt slot {slot} (schedule {event_schedule!r})"),
                }
            region = secondary_regions[secondary_idx]

        return 0, {
            "should_run": "true",
            "region": region,
            "arg": f"--region {region}",
            "label": region,
            "slot": str(slot),
        }

    if requested.lower() in {"", "scheduled"}:
        return 0, {
            "should_run": "true",
            "region": "",
            "arg": "",
            "label": "all",
        }

    if requested.lower() in {"all", "*"}:
        return 0, {
            "should_run": "true",
            "region": "",
            "arg": "",
            "label": "all",
        }

    if requested not in region_names:
        return 1, {
            "error": (
                f"Unknown or disabled region '{requested}'. Enabled regions: {', '.join(region_names) or '(none)'}"
            )
        }

    return 0, {
        "should_run": "true",
        "region": requested,
        "arg": f"--region {requested}",
        "label": requested,
    }


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    if path == DEFAULT_CONFIG_PATH:
        return get_config("job_hunter")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _schedules_from_workflow() -> list[str]:
    """Read cron expressions directly from the local find-jobs.yml workflow file."""
    wf = Path(".github/workflows/find-jobs.yml")
    if not wf.exists():
        return []
    try:
        data = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        triggers = data.get("on") or data.get(True) or {}
        return [s["cron"].strip() for s in (triggers.get("schedule") or []) if s.get("cron")]
    except Exception:
        return []


def main() -> int:
    env_schedules = os.environ.get("HUNT_SCHEDULES", "").strip()
    schedules = hunt_schedules(env_schedules) if env_schedules else _schedules_from_workflow()

    status, outputs = resolve_hunt_region(
        load_config(),
        os.environ.get("EVENT_NAME", ""),
        os.environ.get("EVENT_SCHEDULE", ""),
        os.environ.get("INPUT_REGION", ""),
        schedules,
    )

    if status:
        print(f"::error::{outputs['error']}", file=sys.stderr)
        return status

    for key, value in outputs.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
