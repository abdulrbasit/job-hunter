"""SQLite-backed job store — single source of truth for all job state.

Replaces:
  outputs/state/discovered_urls.yml  (URL dedup)
  outputs/candidates/*.json           (scrape snapshots)
  outputs/applications.yml            (application registry)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_DDL = """
PRAGMA busy_timeout=10000;
PRAGMA journal_mode=DELETE;

CREATE TABLE IF NOT EXISTS jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    url                 TEXT NOT NULL UNIQUE,
    canonical_url       TEXT UNIQUE,
    slug                TEXT UNIQUE,
    status              TEXT NOT NULL DEFAULT 'candidate',
    run_id              TEXT,

    title               TEXT,
    company             TEXT,
    location            TEXT,
    country_code        TEXT,
    snippet             TEXT,
    source              TEXT,
    posted_date_text    TEXT,
    posting_date_status TEXT,
    region              TEXT,
    search_query        TEXT,
    employment_type     TEXT,
    job_description_fetch_status TEXT,
    location_restrictions TEXT,
    ats_platform        TEXT,
    enrichment_source   TEXT,

    score               INTEGER,
    decision            TEXT,
    matched_keywords    TEXT,
    gaps                TEXT,
    role_summary        TEXT,
    score_rationale     TEXT,
    recommendation      TEXT,
    matched_story_ids   TEXT,

    jd_text             TEXT,
    cover_letter_text   TEXT,
    evaluation_text     TEXT,
    resume_pdf_path     TEXT,
    resume_tex_path     TEXT,
    llm_posting_status_check TEXT DEFAULT '',

    notes               TEXT DEFAULT '[]',

    discovered_at       TEXT,
    processed_at        TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_status        ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_run_id        ON jobs(run_id);
CREATE INDEX IF NOT EXISTS idx_jobs_region        ON jobs(region);
CREATE INDEX IF NOT EXISTS idx_jobs_canonical_url ON jobs(canonical_url);
CREATE INDEX IF NOT EXISTS idx_jobs_status_processed_at ON jobs(status, processed_at);
"""

PIPELINE_STATUSES = ("candidate", "discarded", "tailored", "applied", "responded", "interview", "offer", "rejected")
CANONICAL_STATUSES = ("tailored", "applied", "responded", "interview", "offer", "rejected")
ACTIVE_STATUSES = {"tailored", "applied", "responded", "interview", "offer"}
_STATUS_RANK = {status: rank for rank, status in enumerate(PIPELINE_STATUSES)}
_LEGACY_STATUS_ALIASES = {"discovered": "candidate", "processed": "discarded"}


def display_status(raw_status: str) -> str:
    """Translate legacy DB status values to the current vocabulary (no DB migration needed)."""
    return _LEGACY_STATUS_ALIASES.get(raw_status, raw_status)


def _status_rank(status: str) -> int:
    return _STATUS_RANK.get(display_status(status), -1)


def db_path(root: Path) -> Path:
    p = root / "outputs" / "state" / "jobs.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn(root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(root), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    return conn


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for key in ("location_restrictions", "matched_keywords", "gaps", "matched_story_ids", "notes"):
        val = d.get(key)
        if val and isinstance(val, str):
            try:
                d[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
    return d


# ---------------------------------------------------------------------------
# URL dedup — replaces discovered_urls.yml
# ---------------------------------------------------------------------------


def get_all_known_urls(root: Path) -> set[str]:
    """All URLs in DB regardless of status — used to skip re-scraping."""
    with _conn(root) as conn:
        rows = conn.execute("SELECT url, canonical_url FROM jobs").fetchall()
    urls: set[str] = set()
    for row in rows:
        if row["url"]:
            urls.add(row["url"])
        if row["canonical_url"]:
            urls.add(row["canonical_url"])
    return urls


def get_processed_urls(root: Path) -> set[str]:
    """URLs past the candidate stage — used to skip already-handled candidates."""
    with _conn(root) as conn:
        rows = conn.execute(
            "SELECT url, canonical_url FROM jobs WHERE status NOT IN ('candidate', 'discovered')"
        ).fetchall()
    urls: set[str] = set()
    for row in rows:
        if row["url"]:
            urls.add(row["url"])
        if row["canonical_url"]:
            urls.add(row["canonical_url"])
    return urls


# ---------------------------------------------------------------------------
# Broad-discovery candidate URLs — replaces candidate_urls in discovered_urls.yml
# ---------------------------------------------------------------------------


def insert_candidate_urls(root: Path, urls: set[str]) -> None:
    """Insert broad-discovery URLs as status='candidate' (no full job data yet)."""
    from job_hunter.sources.search import canonicalize_url

    now = _now()
    with _conn(root) as conn:
        for url in urls:
            if not url:
                continue
            canonical = canonicalize_url(url) or None
            conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (url, canonical_url, status, discovered_at, created_at, updated_at)
                   VALUES (?, ?, 'candidate', ?, ?, ?)""",
                (url, canonical, now, now, now),
            )


def get_candidate_urls(root: Path) -> set[str]:
    """All known URLs (replaces load_cached_candidate_urls)."""
    return get_all_known_urls(root)


def get_candidate_urls_with_metadata(root: Path) -> dict[str, dict[str, Any]]:
    """All URLs → metadata dict (replaces load_cached_candidate_urls_with_metadata)."""
    with _conn(root) as conn:
        rows = conn.execute("SELECT url, canonical_url, title, company, posted_date_text, snippet FROM jobs").fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["canonical_url"] or row["url"]
        if key:
            result[key] = {k: row[k] for k in ("title", "company", "posted_date_text", "snippet") if row[k]}
    return result


# ---------------------------------------------------------------------------
# Scraped jobs — replaces candidates/*.json snapshots
# ---------------------------------------------------------------------------


def insert_jobs(root: Path, jobs: list[dict[str, Any]], run_id: str = "") -> int:
    """Insert scrape results as status='candidate'. Returns count of new rows."""
    from job_hunter.sources.search import canonicalize_url

    now = _now()
    inserted = 0
    with _conn(root) as conn:
        for job in jobs:
            url = str(job.get("url") or "")
            if not url:
                continue
            canonical = canonicalize_url(url) or None
            loc_r = job.get("location_restrictions")
            mk = job.get("matched_keywords")
            gaps = job.get("gaps")
            employment_type = str(job.get("employment_type") or "")
            country_code = str(job.get("country_code") or "")
            snippet = str(job.get("snippet") or "")
            fetch_status = str(job.get("job_description_fetch_status") or "")

            try:
                conn.execute(
                    """INSERT INTO jobs (
                        url, canonical_url, status, run_id,
                        title, company, location, country_code, snippet, source,
                        posted_date_text, posting_date_status, region, search_query,
                        employment_type, job_description_fetch_status,
                        location_restrictions, ats_platform, enrichment_source,
                        score, matched_keywords, gaps,
                        jd_text, llm_posting_status_check,
                        discovered_at, created_at, updated_at
                    ) VALUES (
                        ?, ?, 'candidate', ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?, ?
                    ) ON CONFLICT(url) DO UPDATE SET
                        run_id          = COALESCE(excluded.run_id, jobs.run_id),
                        employment_type = COALESCE(NULLIF(excluded.employment_type, ''), jobs.employment_type),
                        country_code    = COALESCE(NULLIF(excluded.country_code, ''), jobs.country_code),
                        snippet         = COALESCE(excluded.snippet, jobs.snippet),
                        job_description_fetch_status    = COALESCE(excluded.job_description_fetch_status, jobs.job_description_fetch_status),
                        jd_text         = COALESCE(excluded.jd_text, jobs.jd_text),
                        updated_at      = excluded.updated_at""",
                    (
                        url,
                        canonical,
                        run_id or None,
                        str(job.get("title") or ""),
                        str(job.get("company") or ""),
                        str(job.get("location") or ""),
                        country_code,
                        snippet,
                        str(job.get("source") or ""),
                        str(job.get("posted_date_text") or ""),
                        str(job.get("posting_date_status") or ""),
                        str(job.get("region") or ""),
                        str(job.get("search_query") or ""),
                        employment_type,
                        fetch_status,
                        json.dumps(loc_r) if loc_r is not None else None,
                        str(job.get("ats_platform") or ""),
                        str(job.get("enrichment_source") or ""),
                        job.get("score"),
                        json.dumps(mk) if mk is not None else None,
                        json.dumps(gaps) if gaps is not None else None,
                        snippet,  # jd_text seeded from snippet
                        str(job.get("llm_posting_status_check") or ""),
                        now,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                # A different raw url already maps to this canonical_url (e.g. differs only by a
                # tracking query param). canonical_url is UNIQUE but isn't the INSERT's conflict
                # target, so this row can't be inserted — merge into the existing row instead.
                if canonical is None:
                    raise
                conn.execute(
                    """UPDATE jobs SET
                        run_id          = COALESCE(?, run_id),
                        employment_type = COALESCE(NULLIF(?, ''), employment_type),
                        country_code    = COALESCE(NULLIF(?, ''), country_code),
                        snippet         = COALESCE(NULLIF(?, ''), snippet),
                        job_description_fetch_status = COALESCE(NULLIF(?, ''), job_description_fetch_status),
                        jd_text         = COALESCE(NULLIF(?, ''), jd_text),
                        updated_at      = ?
                       WHERE canonical_url = ?""",
                    (run_id or None, employment_type, country_code, snippet, fetch_status, snippet, now, canonical),
                )
            inserted += 1
    return inserted


def get_discovered_jobs(root: Path, run_id: str | None = None, limit: int = 0) -> list[dict[str, Any]]:
    """Jobs with status='candidate' (or legacy 'discovered') for the agent queue."""
    with _conn(root) as conn:
        if run_id:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status IN ('candidate', 'discovered') AND run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        else:
            q = "SELECT * FROM jobs WHERE status IN ('candidate', 'discovered') ORDER BY created_at"
            if limit:
                q += f" LIMIT {limit}"
            rows = conn.execute(q).fetchall()
    return [_row_to_dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Job lifecycle — replaces applications.yml
# ---------------------------------------------------------------------------


def mark_urls_processed(root: Path, urls: set[str]) -> None:
    """Set status='discarded' for given URLs (dedup mark-as-skipped).

    Inserts a minimal row if the URL is not already in the DB.
    """
    from job_hunter.sources.search import canonicalize_url

    now = _now()
    with _conn(root) as conn:
        for url in urls:
            if not url:
                continue
            canonical = canonicalize_url(url) or None
            conn.execute(
                """INSERT OR IGNORE INTO jobs (url, canonical_url, status, processed_at, created_at, updated_at)
                   VALUES (?, ?, 'discarded', ?, ?, ?)""",
                (url, canonical, now, now, now),
            )
            conn.execute(
                """UPDATE jobs SET status = 'discarded', processed_at = COALESCE(processed_at, ?), updated_at = ?
                   WHERE (url = ? OR canonical_url = ?) AND status IN ('discovered', 'candidate')""",
                (now, now, url, url),
            )


def mark_candidates_discarded(root: Path, entries: list[dict[str, Any]]) -> int:
    """Discard candidate URLs with a reason — deterministic counterpart to mark_urls_processed.

    Each entry is `{"url": ..., "reason": ...}`. Only rows still at status in
    ('candidate', 'discovered', 'discarded') are touched, so a job that already advanced
    past the candidate stage (imported/scored/tailored) is never clobbered. Returns the
    number of URLs marked.
    """
    from job_hunter.sources.search import canonicalize_url

    now = _now()
    marked = 0
    with _conn(root) as conn:
        for entry in entries:
            url = str(entry.get("url") or "")
            if not url:
                continue
            reason = str(entry.get("reason") or "")
            canonical = canonicalize_url(url) or None
            conn.execute(
                """INSERT OR IGNORE INTO jobs (url, canonical_url, status, processed_at, created_at, updated_at)
                   VALUES (?, ?, 'discarded', ?, ?, ?)""",
                (url, canonical, now, now, now),
            )
            row = conn.execute(
                """SELECT id, notes FROM jobs WHERE (url = ? OR canonical_url = ?)
                   AND status IN ('candidate', 'discovered', 'discarded')""",
                (url, url),
            ).fetchone()
            if row is None:
                continue
            notes = json.loads(row["notes"] or "[]")
            if reason and reason not in notes:
                notes.append(reason)
            conn.execute(
                """UPDATE jobs SET status = 'discarded', notes = ?,
                   processed_at = COALESCE(processed_at, ?), updated_at = ? WHERE id = ?""",
                (json.dumps(notes), now, now, row["id"]),
            )
            marked += 1
    return marked


def upsert_job(root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    """Upsert a job (from import-job or application tracking)."""
    from job_hunter.sources.search import canonicalize_url

    url = str(entry.get("url") or "")
    slug = str(entry.get("slug") or "")
    now = _now()

    with _conn(root) as conn:
        existing = None
        if slug:
            existing = conn.execute("SELECT * FROM jobs WHERE slug = ?", (slug,)).fetchone()
        if not existing and url:
            existing = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()

        if existing:
            old_notes = json.loads(existing["notes"] or "[]")
            new_notes = [n for n in list(entry.get("notes") or []) if n and n not in old_notes]
            notes = json.dumps(old_notes + new_notes)
            requested_status = str(entry.get("status") or "")
            resolved_status = (
                requested_status
                if requested_status and _status_rank(requested_status) >= _status_rank(existing["status"])
                else existing["status"]
            )
            conn.execute(
                """UPDATE jobs SET
                    slug            = COALESCE(?, slug),
                    status          = ?,
                    title           = COALESCE(NULLIF(?, ''), title),
                    company         = COALESCE(NULLIF(?, ''), company),
                    location        = COALESCE(NULLIF(?, ''), location),
                    region          = COALESCE(NULLIF(?, ''), region),
                    score           = COALESCE(?, score),
                    decision        = COALESCE(NULLIF(?, ''), decision),
                    job_description_fetch_status    = COALESCE(NULLIF(?, ''), job_description_fetch_status),
                    jd_text         = COALESCE(NULLIF(?, ''), jd_text),
                    resume_pdf_path = COALESCE(NULLIF(?, ''), resume_pdf_path),
                    resume_tex_path = COALESCE(NULLIF(?, ''), resume_tex_path),
                    notes           = ?,
                    processed_at    = COALESCE(processed_at, ?),
                    updated_at      = ?
                   WHERE id = ?""",
                (
                    slug or None,
                    resolved_status,
                    str(entry.get("title") or ""),
                    str(entry.get("company") or ""),
                    str(entry.get("location") or ""),
                    str(entry.get("region") or ""),
                    entry.get("score"),
                    str(entry.get("decision") or ""),
                    str(entry.get("job_description_fetch_status") or ""),
                    str(entry.get("jd_text") or ""),
                    str(entry.get("resume_pdf_path") or ""),
                    str(entry.get("resume_tex_path") or ""),
                    notes,
                    now,
                    now,
                    existing["id"],
                ),
            )
            slug_key = slug or existing["slug"] or ""
            return get_job_by_slug(root, slug_key) or get_job_by_url(root, url) or dict(entry)

        # Insert new
        canonical = canonicalize_url(url) if url else None
        conn.execute(
            """INSERT OR IGNORE INTO jobs (
                url, canonical_url, slug, status,
                title, company, location, region,
                score, decision, job_description_fetch_status, jd_text,
                resume_pdf_path, resume_tex_path,
                notes, discovered_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                url,
                canonical,
                slug or None,
                str(entry.get("status") or "candidate"),
                str(entry.get("title") or ""),
                str(entry.get("company") or ""),
                str(entry.get("location") or ""),
                str(entry.get("region") or ""),
                entry.get("score"),
                str(entry.get("decision") or ""),
                str(entry.get("job_description_fetch_status") or ""),
                str(entry.get("jd_text") or ""),
                str(entry.get("resume_pdf_path") or ""),
                str(entry.get("resume_tex_path") or ""),
                json.dumps(list(entry.get("notes") or [])),
                entry.get("discovered_at") or now,
                entry.get("created_at") or now,
                entry.get("updated_at") or now,
            ),
        )
        return entry


def update_job_status(root: Path, slug: str, status: str, note: str = "") -> dict[str, Any]:
    """Update status for a job by slug."""
    now = _now()
    with _conn(root) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE slug = ?", (slug,)).fetchone()
        if not row:
            raise KeyError(f"job not found: {slug}")
        notes = json.loads(row["notes"] or "[]")
        if note:
            notes.append(note)
        processed_at = now if status == "discarded" and not row["processed_at"] else row["processed_at"]
        conn.execute(
            "UPDATE jobs SET status=?, notes=?, processed_at=?, updated_at=? WHERE slug=?",
            (status, json.dumps(notes), processed_at, now, slug),
        )
    return get_job_by_slug(root, slug) or {}


def set_status_by_id(root: Path, job_id: int, status: str) -> None:
    """Update status for a job by DB id — used for candidates that have no slug yet
    (e.g. discarding from the dashboard before tailoring)."""
    now = _now()
    with _conn(root) as conn:
        row = conn.execute("SELECT processed_at FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise KeyError(f"job not found: id={job_id}")
        processed_at = now if status == "discarded" and not row["processed_at"] else row["processed_at"]
        conn.execute(
            "UPDATE jobs SET status=?, processed_at=?, updated_at=? WHERE id=?",
            (status, processed_at, now, job_id),
        )


def discard_job_ids(root: Path, job_ids: list[int]) -> dict[str, Any]:
    """Batch-discard candidate DB ids in one connection — the dashboard's bulk-discard
    action must be one backend call, not N single-id RPCs each opening its own connection.

    Only rows still at status in ('candidate', 'discovered') are touched — same downgrade
    guard as mark_candidates_discarded — so a stale id for a job already advanced past the
    candidate stage is skipped, never clobbered.
    """
    now = _now()
    discarded = 0
    skipped: list[int] = []
    with _conn(root) as conn:
        for job_id in job_ids:
            row = conn.execute(
                "SELECT processed_at FROM jobs WHERE id = ? AND status IN ('candidate', 'discovered')",
                (job_id,),
            ).fetchone()
            if not row:
                skipped.append(job_id)
                continue
            processed_at = now if not row["processed_at"] else row["processed_at"]
            conn.execute(
                "UPDATE jobs SET status='discarded', processed_at=?, updated_at=? WHERE id=?",
                (processed_at, now, job_id),
            )
            discarded += 1
    return {"discarded": discarded, "skipped": skipped}


def get_jobs(
    root: Path,
    *,
    status: str = "",
    statuses: tuple[str, ...] = (),
    region: str = "",
    since: str = "",
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    elif statuses:
        placeholders = ",".join("?" * len(statuses))
        clauses.append(f"status IN ({placeholders})")
        params.extend(statuses)
    if region:
        clauses.append("LOWER(region) = ?")
        params.append(region.lower())
    if since:
        clauses.append("(discovered_at >= ? OR created_at >= ?)")
        params.extend([since, since])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _conn(root) as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs {where} ORDER BY discovered_at DESC, created_at DESC",  # noqa: S608
            params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


_JOB_LIST_COLUMNS = "id, company, title, location, status, url, discovered_at, created_at"


def get_jobs_summary(root: Path, *, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
    """Lightweight listing query — skips large TEXT columns (jd_text, cover_letter_text,
    evaluation_text) so candidate/discarded list views stay fast as the DB grows."""
    placeholders = ",".join("?" * len(statuses))
    with _conn(root) as conn:
        rows = conn.execute(
            f"SELECT {_JOB_LIST_COLUMNS} FROM jobs WHERE status IN ({placeholders}) "  # noqa: S608
            "ORDER BY discovered_at DESC, created_at DESC",
            statuses,
        ).fetchall()
    return [dict(row) for row in rows]


def get_job_by_slug(root: Path, slug: str) -> dict[str, Any] | None:
    with _conn(root) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE slug = ?", (slug,)).fetchone()
    return _row_to_dict(row) if row else None


def get_job_by_url(root: Path, url: str) -> dict[str, Any] | None:
    with _conn(root) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE url = ? OR canonical_url = ?", (url, url)).fetchone()
    return _row_to_dict(row) if row else None


def delete_job(root: Path, slug: str) -> None:
    with _conn(root) as conn:
        conn.execute("DELETE FROM jobs WHERE slug = ?", (slug,))


def delete_jobs_by_slugs(root: Path, slugs: list[str]) -> int:
    """Delete all matching job rows in one transaction — atomic: all rows are removed
    or (on any error) none are, since the DB write happens inside a single connection
    context that rolls back on exception."""
    if not slugs:
        return 0
    placeholders = ",".join("?" * len(slugs))
    with _conn(root) as conn:
        cursor = conn.execute(f"DELETE FROM jobs WHERE slug IN ({placeholders})", slugs)  # noqa: S608
    return cursor.rowcount


def delete_job_by_id(root: Path, job_id: int) -> None:
    with _conn(root) as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def delete_discarded_older_than(root: Path, days: int = 90) -> int:
    """Delete discarded/legacy-processed rows older than `days`. Never touches
    candidate rows or any post-tailor application status (tailored/applied/etc)."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).replace(microsecond=0).isoformat()
    with _conn(root) as conn:
        cur = conn.execute(
            "DELETE FROM jobs WHERE status IN ('discarded', 'processed') AND COALESCE(processed_at, updated_at) < ?",
            (cutoff,),
        )
    return cur.rowcount


def count_active(root: Path) -> int:
    placeholders = ",".join("?" * len(ACTIVE_STATUSES))
    with _conn(root) as conn:
        row = conn.execute(
            f"SELECT COUNT(*) as n FROM jobs WHERE status IN ({placeholders})",  # noqa: S608
            tuple(ACTIVE_STATUSES),
        ).fetchone()
    return row["n"] if row else 0


def sync_from_job_folders(root: Path) -> int:
    """Back-fill DB from outputs/jobs/*/meta.json (migration aid)."""
    import json as _json

    jobs_dir = root / "outputs" / "jobs"
    if not jobs_dir.exists():
        return 0
    synced = 0
    for meta_path in sorted(jobs_dir.glob("*/meta.json")):
        try:
            meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, _json.JSONDecodeError):
            continue
        slug = meta_path.parent.name
        url = str(meta.get("url") or "")
        if not url:
            continue
        job_dir = meta_path.parent
        entry: dict[str, Any] = {
            "slug": slug,
            "url": url,
            "title": meta.get("title") or "",
            "company": meta.get("company") or "",
            "location": meta.get("location") or "",
            "region": meta.get("region") or "",
            "job_description_fetch_status": meta.get("job_description_fetch_status") or "",
            # upsert_job only promotes forward (never demotes an already-advanced job)
            "status": "tailored",
        }
        # Read jd.md if present
        jd_path = job_dir / "jd.md"
        if jd_path.exists():
            entry["jd_text"] = jd_path.read_text(encoding="utf-8")
        # Read file paths
        for pdf in (job_dir / "resume_tailored.pdf",):
            if pdf.exists():
                entry["resume_pdf_path"] = f"outputs/jobs/{slug}/{pdf.name}"
        for tex in (job_dir / "resume_tailored.tex",):
            if tex.exists():
                entry["resume_tex_path"] = f"outputs/jobs/{slug}/{tex.name}"
        upsert_job(root, entry)
        synced += 1
    return synced


def set_llm_posting_status_check(root: Path, url: str, result: str) -> None:
    """Store advisory open-check result ('open'|'closed'|'unknown') for a job URL."""
    now = _now()
    with _conn(root) as conn:
        conn.execute(
            "UPDATE jobs SET llm_posting_status_check = ?, updated_at = ? WHERE url = ? OR canonical_url = ?",
            (result, now, url, url),
        )
