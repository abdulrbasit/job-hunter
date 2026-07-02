"""SQLite-backed job store — single source of truth for all job state.

Replaces:
  outputs/state/discovered_urls.yml  (URL dedup)
  outputs/candidates/*.json           (scrape snapshots)
  outputs/applications.yml            (application registry)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    url                 TEXT NOT NULL UNIQUE,
    canonical_url       TEXT UNIQUE,
    slug                TEXT UNIQUE,
    status              TEXT NOT NULL DEFAULT 'discovered',
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
"""

CANONICAL_STATUSES = ("tailored", "applied", "responded", "interview", "offer", "rejected")
ACTIVE_STATUSES = {"tailored", "applied", "responded", "interview", "offer"}
_PROCESSED_STATUSES = {"discovered", "processed", "tailored", "applied", "responded", "interview", "offer", "rejected"}


def db_path(root: Path) -> Path:
    p = root / "outputs" / "state" / "jobs.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn(root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(root))
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
    """URLs processed by agent (past 'discovered') — used to skip already-handled candidates."""
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
    """Insert scrape results as status='discovered'. Returns count of new rows."""
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
                    ?, ?, 'discovered', ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?
                ) ON CONFLICT(url) DO UPDATE SET
                    status          = CASE WHEN jobs.status = 'candidate' THEN 'discovered' ELSE jobs.status END,
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
                    str(job.get("country_code") or ""),
                    str(job.get("snippet") or ""),
                    str(job.get("source") or ""),
                    str(job.get("posted_date_text") or ""),
                    str(job.get("posting_date_status") or ""),
                    str(job.get("region") or ""),
                    str(job.get("search_query") or ""),
                    str(job.get("employment_type") or ""),
                    str(job.get("job_description_fetch_status") or ""),
                    json.dumps(loc_r) if loc_r is not None else None,
                    str(job.get("ats_platform") or ""),
                    str(job.get("enrichment_source") or ""),
                    job.get("score"),
                    json.dumps(mk) if mk is not None else None,
                    json.dumps(gaps) if gaps is not None else None,
                    str(job.get("snippet") or ""),  # jd_text seeded from snippet
                    str(job.get("llm_posting_status_check") or ""),
                    now,
                    now,
                    now,
                ),
            )
            inserted += 1
    return inserted


def get_discovered_jobs(root: Path, run_id: str | None = None, limit: int = 0) -> list[dict[str, Any]]:
    """Jobs with status='discovered' for the agent queue."""
    with _conn(root) as conn:
        if run_id:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = 'discovered' AND run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        else:
            q = "SELECT * FROM jobs WHERE status = 'discovered' ORDER BY created_at"
            if limit:
                q += f" LIMIT {limit}"
            rows = conn.execute(q).fetchall()
    return [_row_to_dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Job lifecycle — replaces applications.yml
# ---------------------------------------------------------------------------


def mark_urls_processed(root: Path, urls: set[str]) -> None:
    """Set status='processed' for given URLs (dedup mark-as-done).

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
                   VALUES (?, ?, 'processed', ?, ?, ?)""",
                (url, canonical, now, now, now),
            )
            conn.execute(
                """UPDATE jobs SET status = 'processed', processed_at = COALESCE(processed_at, ?), updated_at = ?
                   WHERE (url = ? OR canonical_url = ?) AND status IN ('discovered', 'candidate')""",
                (now, now, url, url),
            )


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
                    str(entry.get("status") or existing["status"]),
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
                str(entry.get("status") or "discovered"),
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
        processed_at = now if status == "processed" and not row["processed_at"] else row["processed_at"]
        conn.execute(
            "UPDATE jobs SET status=?, notes=?, processed_at=?, updated_at=? WHERE slug=?",
            (status, json.dumps(notes), processed_at, now, slug),
        )
    return get_job_by_slug(root, slug) or {}


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


def delete_job_by_id(root: Path, job_id: int) -> None:
    with _conn(root) as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


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
        existing = get_job_by_slug(root, slug) or get_job_by_url(root, url)
        entry: dict[str, Any] = {
            "slug": slug,
            "url": url,
            "title": meta.get("title") or "",
            "company": meta.get("company") or "",
            "location": meta.get("location") or "",
            "region": meta.get("region") or "",
            "job_description_fetch_status": meta.get("job_description_fetch_status") or "",
            "status": existing["status"] if existing else "tailored",
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
