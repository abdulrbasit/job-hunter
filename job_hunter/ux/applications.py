"""Canonical application lifecycle tracker for Job Hunter."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypedDict

import yaml

from job_hunter.agent_context._utils import _read_yaml
from job_hunter.tracker import repo_path

CANONICAL_STATUSES = (
    "tailored",
    "applied",
    "responded",
    "interview",
    "offer",
    "rejected",
)

ACTIVE_STATUSES = {"tailored", "applied", "responded", "interview", "offer"}
HIDDEN_LEGACY_STATUSES = {"discarded", "skip"}


class ApplicationRecord(TypedDict, total=False):
    slug: str
    date: str
    company: str
    title: str
    url: str
    region: str
    location: str
    status: str
    score: int | float | str | None
    decision: str
    files: dict[str, str]
    notes: list[str]
    created_at: str
    updated_at: str


def applications_path(root: Path | None = None) -> Path:
    base = root or repo_path()
    return base / "outputs" / "applications.yml"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def normalize_status(status: str) -> str:
    normalized = str(status or "").strip().lower().replace("-", "_")
    aliases = {
        "evaluate": "tailored",
        "evaluated": "tailored",
        "tailor": "tailored",
        "application_sent": "applied",
        "reply": "responded",
        "screen": "interview",
        "onsite": "interview",
        "declined": "rejected",
        "discard": "rejected",
        "discarded": "rejected",
        "skip": "rejected",
        "skipped": "rejected",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in CANONICAL_STATUSES:
        raise ValueError(f"invalid status '{status}'. Expected one of: {', '.join(CANONICAL_STATUSES)}")
    return normalized


def load_applications(root: Path | None = None) -> dict[str, Any]:
    path = applications_path(root)
    if not path.exists():
        return {"applications": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    apps = data.get("applications", [])
    if not isinstance(apps, list):
        apps = []
    return {"applications": apps}


def save_applications(data: dict[str, Any], root: Path | None = None) -> Path:
    path = applications_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"applications": list(data.get("applications", []) or [])}
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    return path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _first_existing(job_dir: Path, names: tuple[str, ...]) -> str:
    for name in names:
        if (job_dir / name).exists():
            return f"outputs/jobs/{job_dir.name}/{name}"
    return ""


def application_from_job(
    slug: str,
    *,
    root: Path | None = None,
    status: str = "tailored",
    note: str = "",
) -> dict[str, Any]:
    base = root or repo_path()
    job_dir = base / "outputs" / "jobs" / slug
    meta = _read_json(job_dir / "meta.json")
    score = _read_yaml(job_dir / "score.yml")
    now = utc_now()
    return {
        "slug": slug,
        "date": meta.get("date") or date.today().isoformat(),
        "company": meta.get("company") or "Unknown Company",
        "title": meta.get("title") or "Unknown Role",
        "url": meta.get("url") or "",
        "region": meta.get("region") or "",
        "location": meta.get("location") or "",
        "status": normalize_status(status),
        "score": score.get("score"),
        "decision": score.get("decision") or score.get("status") or "",
        "files": {
            "job_dir": f"outputs/jobs/{slug}/",
            "resume_pdf": _first_existing(job_dir, ("resume_tailored.pdf",)),
            "resume_tex": _first_existing(job_dir, ("resume_tailored.tex",)),
            "cover_letter": _first_existing(job_dir, ("cover_letter.md",)),
            "evaluation": _first_existing(job_dir, ("evaluation.md",)),
        },
        "notes": [note] if note else [],
        "created_at": now,
        "updated_at": now,
    }


def _status_from_score(score: dict[str, Any]) -> str:
    decision = str(score.get("decision") or score.get("status") or "").strip().lower()
    skip_decisions = {
        "decline",
        "declined",
        "discard",
        "discarded",
        "do not apply",
        "do_not_apply",
        "no",
        "no_apply",
        "reject",
        "rejected",
        "skip",
        "skipped",
    }
    return "" if decision in skip_decisions else "tailored"


def backfill_applications_from_jobs(root: Path | None = None) -> list[dict[str, Any]]:
    base = root or repo_path()
    jobs_dir = base / "outputs" / "jobs"
    if not jobs_dir.exists():
        return []
    created: list[dict[str, Any]] = []
    for job_dir in sorted(path for path in jobs_dir.iterdir() if path.is_dir()):
        score = _read_yaml(job_dir / "score.yml")
        status = _status_from_score(score)
        if not status:
            continue
        entry = application_from_job(
            job_dir.name,
            root=base,
            status=status,
            note="Backfilled from existing job folder",
        )
        created.append(upsert_application(entry, root=base))
    return created


def ensure_applications(root: Path | None = None) -> dict[str, Any]:
    data = load_applications(root)
    if data["applications"]:
        return data
    backfill_applications_from_jobs(root)
    return load_applications(root)


def upsert_application(entry: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    data = load_applications(root)
    apps = data["applications"]
    key_slug = str(entry.get("slug") or "")
    key_url = str(entry.get("url") or "")
    now = utc_now()
    for idx, app in enumerate(apps):
        if (key_slug and app.get("slug") == key_slug) or (key_url and app.get("url") == key_url):
            merged = {**app, **entry}
            old_notes = list(app.get("notes") or [])
            new_notes = [n for n in list(entry.get("notes") or []) if n and n not in old_notes]
            merged["notes"] = old_notes + new_notes
            merged["created_at"] = app.get("created_at") or entry.get("created_at") or now
            merged["updated_at"] = now
            apps[idx] = merged
            save_applications(data, root)
            return merged
    apps.append(entry)
    save_applications(data, root)
    return entry


def upsert_application_from_job(
    slug: str,
    *,
    root: Path | None = None,
    status: str = "tailored",
    note: str = "",
) -> dict[str, Any]:
    return upsert_application(
        application_from_job(slug, root=root, status=status, note=note),
        root=root,
    )


def update_application_status(
    slug: str,
    status: str,
    *,
    root: Path | None = None,
    note: str = "",
) -> dict[str, Any]:
    data = load_applications(root)
    target_status = normalize_status(status)
    for app in data["applications"]:
        if app.get("slug") == slug:
            app["status"] = target_status
            app["updated_at"] = utc_now()
            if note:
                notes = list(app.get("notes") or [])
                notes.append(note)
                app["notes"] = notes
            save_applications(data, root)
            return app
    raise KeyError(f"application not found: {slug}")


def filtered_applications(
    *,
    root: Path | None = None,
    status: str = "",
    region: str = "",
    since: str = "",
) -> list[dict[str, Any]]:
    apps = ensure_applications(root)["applications"]
    apps = [
        app
        for app in apps
        if str(app.get("status") or "") in CANONICAL_STATUSES
        and str(app.get("status") or "") not in HIDDEN_LEGACY_STATUSES
    ]
    if status:
        wanted = normalize_status(status)
        apps = [app for app in apps if app.get("status") == wanted]
    if region:
        apps = [app for app in apps if str(app.get("region") or "").lower() == region.lower()]
    if since:
        apps = [app for app in apps if str(app.get("date") or "") >= since]
    return sorted(
        apps,
        key=lambda app: (
            str(app.get("date") or ""),
            str(app.get("company") or ""),
        ),
        reverse=True,
    )


def active_application_count(root: Path | None = None) -> int:
    return sum(
        1 for app in ensure_applications(root)["applications"] if str(app.get("status") or "") in ACTIVE_STATUSES
    )


def render_applications_table(apps: list[dict[str, Any]]) -> str:
    rows = ["Date       Status      Score  Region       Company - Role"]
    rows.append("-" * 78)
    for app in apps:
        score = app.get("score")
        score_text = "" if score in (None, "") else str(score)
        role = f"{app.get('company', 'Unknown')} - {app.get('title', 'Unknown')}"
        rows.append(
            f"{str(app.get('date') or '')[:10]:<10} "
            f"{str(app.get('status') or ''):<11} "
            f"{score_text:<6} "
            f"{str(app.get('region') or app.get('location') or '')[:12]:<12} "
            f"{role}"
        )
    return "\n".join(rows)
