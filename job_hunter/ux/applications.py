"""Canonical application lifecycle tracker for Job Hunter."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypedDict

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
    from job_hunter.db.jobs import get_jobs

    base = root or repo_path()
    apps = get_jobs(base, statuses=CANONICAL_STATUSES)
    return {"applications": apps}


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
    jd_path = job_dir / "jd.md"
    jd_text = jd_path.read_text(encoding="utf-8") if jd_path.exists() else ""
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
        "fetch_status": meta.get("fetch_status") or "",
        "jd_text": jd_text,
        "resume_pdf_path": _first_existing(job_dir, ("resume_tailored.pdf",)),
        "resume_tex_path": _first_existing(job_dir, ("resume_tailored.tex",)),
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
    from job_hunter.db.jobs import sync_from_job_folders

    base = root or repo_path()
    synced = sync_from_job_folders(base)
    return [{"synced": synced}]


def ensure_applications(root: Path | None = None) -> dict[str, Any]:
    return load_applications(root)


def upsert_application(entry: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    from job_hunter.db.jobs import upsert_job

    base = root or repo_path()
    return upsert_job(base, entry)


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
    from job_hunter.db.jobs import update_job_status

    base = root or repo_path()
    target_status = normalize_status(status)
    app = update_job_status(base, slug, target_status, note)
    apps = load_applications(base)["applications"]
    from job_hunter.pipeline.readme_writer import update_readme_from_applications

    update_readme_from_applications(apps, base, date.today().isoformat())
    return app


def filtered_applications(
    *,
    root: Path | None = None,
    status: str = "",
    region: str = "",
    since: str = "",
) -> list[dict[str, Any]]:
    from job_hunter.db.jobs import get_jobs

    base = root or repo_path()
    apps = get_jobs(
        base,
        status=normalize_status(status) if status else "",
        statuses=CANONICAL_STATUSES if not status else (),
        region=region,
        since=since,
    )
    apps = [app for app in apps if str(app.get("status") or "") not in HIDDEN_LEGACY_STATUSES]
    return sorted(
        apps,
        key=lambda app: (
            str(app.get("discovered_at") or app.get("created_at") or ""),
            str(app.get("company") or ""),
        ),
        reverse=True,
    )


def delete_application(slug: str, root: Path | None = None) -> None:
    import logging
    import shutil

    from job_hunter.db.jobs import delete_job

    base = root or repo_path()
    delete_job(base, slug)
    job_dir = base / "outputs" / "jobs" / slug
    if job_dir.exists():
        try:
            shutil.rmtree(job_dir)
        except OSError as exc:
            logging.getLogger(__name__).warning(
                "[delete] Could not remove %s: %s — delete manually to prevent agent from re-suggesting it.",
                job_dir,
                exc,
            )
    apps = load_applications(base)["applications"]
    from job_hunter.pipeline.readme_writer import update_readme_from_applications

    update_readme_from_applications(apps, base, date.today().isoformat())


def active_application_count(root: Path | None = None) -> int:
    from job_hunter.db.jobs import count_active

    return count_active(root or repo_path())


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
