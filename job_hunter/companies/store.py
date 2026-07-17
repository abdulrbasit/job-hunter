"""Runtime SQLite company store — outputs/state/companies.db.

Regenerable, per-machine, not synced: catalog rows are re-imported from the bundled
seed (job_hunter.companies.seed) on every version bump; user rows are mirrored 1:1
from config/job_hunter.yml's companies.targets (the durable, git-synced source of
truth for a user's own companies — see job_hunter.config.service).

Uniqueness is (normalized_url, country, source) rather than a bare normalized_url:
one company can have office/eligibility in several countries (sharded into separate
rows), and a user target may intentionally shadow a catalog row with the same URL —
candidate_companies() below is what dedupes those, preferring the user row.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_hunter.tracking.repository import AutoCloseConnection

_DDL = """
PRAGMA busy_timeout=10000;
PRAGMA journal_mode=DELETE;

CREATE TABLE IF NOT EXISTS companies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_id      TEXT,
    name            TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    url             TEXT NOT NULL,
    normalized_url  TEXT NOT NULL,
    country         TEXT NOT NULL,
    city            TEXT,
    industry        TEXT NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('catalog', 'user')),
    batch           TEXT NOT NULL DEFAULT '',
    enabled         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (normalized_url, country, source)
);

CREATE INDEX IF NOT EXISTS idx_companies_country      ON companies(country);
CREATE INDEX IF NOT EXISTS idx_companies_country_city ON companies(country, city);
CREATE INDEX IF NOT EXISTS idx_companies_industry     ON companies(industry);
CREATE INDEX IF NOT EXISTS idx_companies_catalog_id   ON companies(catalog_id);

CREATE TABLE IF NOT EXISTS companies_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def db_path(root: Path) -> Path:
    p = root / "outputs" / "state" / "companies.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn(root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(root), timeout=10, factory=AutoCloseConnection)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    return conn


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def _normalize_name(name: str) -> str:
    return name.strip().casefold()


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM companies_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO companies_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def ensure_seeded(root: Path) -> bool:
    """(Re-)import the bundled catalog if the wheel's seed version has changed.

    Preserves each catalog row's `enabled` flag across a re-seed by keying on
    (normalized_url, country) — a version bump replaces the underlying data but
    not the user's opt-in choices. User rows (source='user') are untouched.
    """
    from job_hunter.companies import seed

    version = seed.manifest()["version"]
    with _conn(root) as conn:
        if _meta_get(conn, "seed_version") == version:
            return False
        now = _now()
        enabled_keys = {
            (row["normalized_url"], row["country"])
            for row in conn.execute(
                "SELECT normalized_url, country FROM companies WHERE source = 'catalog' AND enabled = 1"
            )
        }
        conn.execute("DELETE FROM companies WHERE source = 'catalog'")
        rows = []
        for catalog_id, name, url, country, industry in seed.iter_seed_rows():
            normalized_url = _normalize_url(url)
            enabled = 1 if (normalized_url, country) in enabled_keys else 0
            rows.append(
                (
                    catalog_id,
                    name,
                    _normalize_name(name),
                    url,
                    normalized_url,
                    country,
                    industry,
                    "catalog",
                    version,
                    enabled,
                    now,
                    now,
                )
            )
        conn.executemany(
            """INSERT INTO companies
               (catalog_id, name, normalized_name, url, normalized_url, country, industry,
                source, batch, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        _meta_set(conn, "seed_version", version)
    return True


def sync_user_targets(root: Path, targets: list[dict[str, Any]]) -> None:
    """Replace all source='user' rows with a mirror of config/job_hunter.yml's companies.targets."""
    from job_hunter.locations import city_by_name_exact

    now = _now()
    rows = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        name = str(target.get("name") or "").strip()
        url = str(target.get("url") or "").strip()
        country = str(target.get("country") or "").strip().upper()
        if not (name and url and country):
            continue
        city = str(target.get("city") or "").strip() or None
        if city:
            resolved = city_by_name_exact(country, city)
            city = resolved.id if resolved else None
        industry = str(target.get("industry") or "").strip() or "other"
        enabled = 0 if target.get("enabled") is False else 1
        normalized_url = _normalize_url(url)
        rows.append(
            (
                None,
                name,
                _normalize_name(name),
                url,
                normalized_url,
                country,
                city,
                industry,
                "user",
                "config",
                enabled,
                now,
                now,
            )
        )
    with _conn(root) as conn:
        conn.execute("DELETE FROM companies WHERE source = 'user'")
        conn.executemany(
            """INSERT INTO companies
               (catalog_id, name, normalized_name, url, normalized_url, country, city, industry,
                source, batch, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )


def _build_where(
    *,
    country: str = "",
    city: str = "",
    industry: str = "",
    enabled: bool | None = None,
    source: str = "",
    search: str = "",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if country:
        clauses.append("country = ?")
        params.append(country.strip().upper())
    if city:
        clauses.append("city = ?")
        params.append(city)
    if industry:
        clauses.append("industry = ?")
        params.append(industry)
    if enabled is not None:
        clauses.append("enabled = ?")
        params.append(1 if enabled else 0)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if search.strip():
        clauses.append("normalized_name LIKE ?")
        params.append(f"%{_normalize_name(search)}%")
    return (" AND ".join(clauses) if clauses else "1=1"), params


def query_page(
    root: Path,
    *,
    country: str = "",
    city: str = "",
    industry: str = "",
    enabled: bool | None = None,
    source: str = "",
    search: str = "",
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    where, params = _build_where(
        country=country, city=city, industry=industry, enabled=enabled, source=source, search=search
    )
    page = max(1, page)
    page_size = min(500, max(1, page_size))
    with _conn(root) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM companies WHERE {where}", params).fetchone()[0]  # noqa: S608
        rows = conn.execute(
            f"SELECT * FROM companies WHERE {where} ORDER BY name LIMIT ? OFFSET ?",  # noqa: S608
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


def candidate_companies(
    root: Path, *, countries: list[str] | None, excluded_industries: Iterable[str] = ()
) -> list[dict[str, Any]]:
    """Enabled companies eligible for a hunt: gated by country and industry exclusion.

    `countries=None` means every country is allowed (a remote_global region is enabled);
    `countries=[]` means no region is enabled, so nothing matches. When a user target and
    a catalog row share the same (normalized_url, country), the user row wins — same
    override semantics as the old career_pages.yml custom-entry-wins rule.
    """
    if countries is not None and not countries:
        return []
    where = ["enabled = 1"]
    params: list[Any] = []
    if countries is not None:
        where.append(f"country IN ({','.join('?' * len(countries))})")
        params.extend(countries)
    excluded = list(excluded_industries)
    if excluded:
        where.append(f"industry NOT IN ({','.join('?' * len(excluded))})")
        params.extend(excluded)
    sql = f"SELECT * FROM companies WHERE {' AND '.join(where)} ORDER BY source DESC, id"  # noqa: S608
    with _conn(root) as conn:
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    seen: set[tuple[str, str]] = set()
    result = []
    for row in rows:  # source DESC: 'user' sorts before 'catalog' — user override wins.
        key = (row["normalized_url"], row["country"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def set_enabled(root: Path, ids: list[int], enabled: bool) -> int:
    if not ids:
        return 0
    with _conn(root) as conn:
        cursor = conn.execute(
            f"UPDATE companies SET enabled = ?, updated_at = ? WHERE id IN ({','.join('?' * len(ids))})",  # noqa: S608
            [1 if enabled else 0, _now(), *ids],
        )
        return cursor.rowcount


def set_enabled_where(
    root: Path,
    *,
    new_enabled: bool,
    country: str = "",
    city: str = "",
    industry: str = "",
    enabled: bool | None = None,
    source: str = "",
    search: str = "",
) -> int:
    where, params = _build_where(
        country=country, city=city, industry=industry, enabled=enabled, source=source, search=search
    )
    with _conn(root) as conn:
        cursor = conn.execute(
            f"UPDATE companies SET enabled = ?, updated_at = ? WHERE {where}",  # noqa: S608
            [1 if new_enabled else 0, _now(), *params],
        )
        return cursor.rowcount


def set_enabled_by_catalog_ids(root: Path, catalog_ids: list[str], enabled: bool) -> int:
    if not catalog_ids:
        return 0
    with _conn(root) as conn:
        cursor = conn.execute(
            f"""UPDATE companies SET enabled = ?, updated_at = ?
                WHERE source = 'catalog' AND catalog_id IN ({",".join("?" * len(catalog_ids))})""",  # noqa: S608
            [1 if enabled else 0, _now(), *catalog_ids],
        )
        return cursor.rowcount


def get_by_id(root: Path, company_id: int) -> dict[str, Any] | None:
    with _conn(root) as conn:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    return dict(row) if row is not None else None


def industry_counts(root: Path, *, source: str = "") -> list[dict[str, Any]]:
    where, params = _build_where(source=source)
    with _conn(root) as conn:
        rows = conn.execute(
            f"SELECT industry, COUNT(*) AS count FROM companies WHERE {where} GROUP BY industry ORDER BY count DESC",  # noqa: S608
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def distinct_countries(root: Path, *, source: str = "") -> list[str]:
    where, params = _build_where(source=source)
    with _conn(root) as conn:
        rows = conn.execute(
            f"SELECT DISTINCT country FROM companies WHERE {where} ORDER BY country",  # noqa: S608
            params,
        ).fetchall()
    return [row[0] for row in rows]


def company_count(root: Path, *, enabled: bool | None = None, source: str = "", industry: str = "") -> int:
    where, params = _build_where(enabled=enabled, source=source, industry=industry)
    with _conn(root) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM companies WHERE {where}", params).fetchone()[0]  # noqa: S608
