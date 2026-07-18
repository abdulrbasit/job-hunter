"""Canonical application lifecycle state — the query/mutation API for outputs/jobs/*.

Pure state: read/write job records. Report generation (README, dashboards) is
triggered by callers after a mutation, not by this module.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypedDict

from job_hunter.core.utils import read_yaml
from job_hunter.tracker import repo_path
from job_hunter.tracking.repository import (
    ACTIVE_STATUSES,  # noqa: F401  (re-exported for job_hunter.agent_context.batch)
    CANONICAL_STATUSES,
    PIPELINE_STATUSES,
    display_status,
)

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
        "saved": "shortlisted",
        "shortlist": "shortlisted",
        "evaluate": "tailored",
        "evaluated": "tailored",
        "tailor": "tailored",
        "application_sent": "applied",
        "reply": "responded",
        "screen": "interview",
        "onsite": "interview",
        "decline": "discarded",
        "declined": "discarded",
        "discard": "discarded",
        "skip": "discarded",
        "skipped": "discarded",
        "discovered": "candidate",
        "processed": "discarded",
    }
    normalized = display_status(aliases.get(normalized, normalized))
    if normalized not in PIPELINE_STATUSES:
        raise ValueError(f"invalid status '{status}'. Expected one of: {', '.join(PIPELINE_STATUSES)}")
    return normalized


def load_applications(root: Path | None = None) -> dict[str, Any]:
    from job_hunter.tracking.repository import get_jobs

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
    score = read_yaml(job_dir / "score.yml")
    _require_apply_score(score, slug)
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
        "job_description_fetch_status": meta.get("job_description_fetch_status") or "",
        "jd_text": jd_text,
        "resume_pdf_path": _first_existing(job_dir, ("resume_tailored.pdf",)),
        "resume_tex_path": _first_existing(job_dir, ("resume_tailored.tex",)),
        "notes": [note] if note else [],
        "created_at": now,
        "updated_at": now,
    }


def _require_apply_score(score: dict[str, Any], slug: str) -> None:
    """Refuse to build an application entry unless score.yml has a numeric score and
    decision APPLY. A SKIP decision, a missing score.yml, or a missing score value must
    never produce a 'tailored' application row (there is nothing to apply with)."""
    decision = str(score.get("decision") or score.get("status") or "").strip().upper()
    score_value = score.get("score")
    valid_score = isinstance(score_value, int) and not isinstance(score_value, bool)
    if decision != "APPLY" or not valid_score:
        raise ValueError(
            f"refusing to create an application for {slug!r}: score.yml is missing, has no valid "
            "numeric score, or decision is not APPLY"
        )


def backfill_applications_from_jobs(root: Path | None = None) -> list[dict[str, Any]]:
    from job_hunter.tracking.repository import sync_from_job_folders

    base = root or repo_path()
    synced = sync_from_job_folders(base)
    return [{"synced": synced}]


def ensure_applications(root: Path | None = None) -> dict[str, Any]:
    return load_applications(root)


def upsert_application(entry: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    from job_hunter.tracking.repository import upsert_job

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
    """Update an application's status. Callers that need the README refreshed must call
    pipeline.stages.readme.update_readme_from_applications() themselves after this returns."""
    from job_hunter.tracking.repository import update_job_status

    base = root or repo_path()
    target_status = normalize_status(status)
    return update_job_status(base, slug, target_status, note)


def filtered_applications(
    *,
    root: Path | None = None,
    status: str = "",
    region: str = "",
    since: str = "",
) -> list[dict[str, Any]]:
    from job_hunter.tracking.repository import get_jobs

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


def _resolve_job_dir_for_delete(jobs_root: Path, slug: str) -> Path | None:
    """Return slug's job dir if it resolves to a direct child of jobs_root, else None
    (rejects '', '..', absolute paths, and anything else that would escape jobs_root)."""
    if not slug:
        return None
    job_dir = (jobs_root / slug).resolve()
    return job_dir if job_dir.parent == jobs_root and job_dir.is_relative_to(jobs_root) else None


def delete_applications_batch(slugs: list[str], root: Path | None = None) -> dict[str, Any]:
    """Delete application DB records and job folders for multiple slugs in one DB batch.

    Job folders are staged (renamed aside) before the DB batch delete runs; if that
    delete raises, every staged folder is moved back so disk and DB never disagree.
    Once the DB delete has committed, staged folders are discarded for good. Missing
    folders are tolerated, matching the pre-batch single-delete behavior.
    """
    import logging
    import shutil
    import uuid
    from contextlib import suppress

    from job_hunter.tracking.repository import delete_jobs_by_slugs

    base = root or repo_path()
    jobs_root = (base / "outputs" / "jobs").resolve()
    logger = logging.getLogger(__name__)

    valid_slugs: list[str] = []
    skipped: list[str] = []
    job_dirs: dict[str, Path] = {}
    for slug in slugs:
        job_dir = _resolve_job_dir_for_delete(jobs_root, slug)
        if job_dir is None:
            skipped.append(slug)
        else:
            valid_slugs.append(slug)
            job_dirs[slug] = job_dir

    stage_dir = base / "outputs" / "state" / f".delete_staging_{uuid.uuid4().hex}"
    staged: dict[str, Path] = {}
    warnings: list[str] = []
    for slug in valid_slugs:
        job_dir = job_dirs[slug]
        if not job_dir.exists():
            continue
        try:
            stage_dir.mkdir(parents=True, exist_ok=True)
            dest = stage_dir / slug
            shutil.move(str(job_dir), str(dest))
            staged[slug] = dest
        except OSError as exc:
            warnings.append(f"{slug}: could not stage job folder for deletion ({exc})")

    try:
        deleted = delete_jobs_by_slugs(base, valid_slugs)
    except Exception:
        for slug, dest in staged.items():
            with suppress(OSError):
                shutil.move(str(dest), str(job_dirs[slug]))
        with suppress(OSError):
            shutil.rmtree(stage_dir)
        raise

    for slug, dest in staged.items():
        try:
            shutil.rmtree(dest)
        except OSError as exc:
            logger.warning(
                "[delete-batch] Could not remove staged folder for %s: %s — delete %s manually.", slug, exc, dest
            )
    with suppress(OSError):
        stage_dir.rmdir()

    return {"deleted": deleted, "skipped": skipped, "warnings": warnings}


def delete_application(slug: str, root: Path | None = None) -> None:
    """Delete an application's DB record and job folder. Callers that need the README
    refreshed must call pipeline.stages.readme.update_readme_from_applications() themselves after this."""
    delete_applications_batch([slug], root=root)


def active_application_count(root: Path | None = None) -> int:
    from job_hunter.tracking.repository import count_active

    return count_active(root or repo_path())
