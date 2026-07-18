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
    company_type    TEXT NOT NULL DEFAULT 'unknown',
    funding_stage   TEXT,
    source          TEXT NOT NULL CHECK (source IN ('catalog', 'user')),
    batch           TEXT NOT NULL DEFAULT '',
    enabled         INTEGER NOT NULL DEFAULT 0,
    needs_review    INTEGER NOT NULL DEFAULT 0,
    review_reason   TEXT NOT NULL DEFAULT '',
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
    existing = {row[1] for row in conn.execute("PRAGMA table_info(companies)")}
    if "company_type" not in existing:
        conn.execute("ALTER TABLE companies ADD COLUMN company_type TEXT NOT NULL DEFAULT 'unknown'")
    if "funding_stage" not in existing:
        conn.execute("ALTER TABLE companies ADD COLUMN funding_stage TEXT")
    if "needs_review" not in existing:
        conn.execute("ALTER TABLE companies ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0")
    if "review_reason" not in existing:
        conn.execute("ALTER TABLE companies ADD COLUMN review_reason TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_companies_type_stage ON companies(company_type, funding_stage)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_companies_needs_review ON companies(needs_review)")
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
        # Rows the user resolved out of the review queue carry local fixes (industry/url)
        # the bundle doesn't have — preserve them across the re-seed, keyed like `enabled`.
        resolved = {
            (row["normalized_url"], row["country"]): dict(row)
            for row in conn.execute("SELECT * FROM companies WHERE source = 'catalog' AND needs_review = 0")
        }
        conn.execute("DELETE FROM companies WHERE source = 'catalog'")
        rows = []
        main_keys: set[tuple[str, str]] = set()
        for company in seed.iter_seed_companies():
            url = company.career_url
            country = company.country
            normalized_url = _normalize_url(url)
            main_keys.add((normalized_url, country))
            enabled = 1 if (normalized_url, country) in enabled_keys else 0
            rows.append(
                (
                    company.catalog_id,
                    company.name,
                    _normalize_name(company.name),
                    url,
                    normalized_url,
                    country,
                    company.city or None,
                    company.industry,
                    company.company_type.value,
                    company.funding_stage.value if company.funding_stage else None,
                    "catalog",
                    version,
                    enabled,
                    0,
                    "",
                    now,
                    now,
                )
            )
        for item in seed.iter_review_companies():
            url = str(item.get("url") or "")
            country = str(item.get("country") or "")
            normalized_url = _normalize_url(url)
            key = (normalized_url, country)
            if key in main_keys:
                continue  # the bundle promoted this row out of review
            main_keys.add(key)
            prior = resolved.get(key)
            if prior is not None:
                rows.append(
                    (
                        prior["catalog_id"],
                        prior["name"],
                        prior["normalized_name"],
                        prior["url"],
                        prior["normalized_url"],
                        country,
                        prior["city"],
                        prior["industry"],
                        prior["company_type"],
                        prior["funding_stage"],
                        "catalog",
                        version,
                        prior["enabled"],
                        0,
                        "",
                        now,
                        now,
                    )
                )
                continue
            name = str(item.get("name") or "")
            rows.append(
                (
                    str(item.get("id") or "") or None,
                    name,
                    _normalize_name(name),
                    url,
                    normalized_url,
                    country,
                    str(item.get("city") or "") or None,
                    str(item.get("industry") or "") or "other",
                    str(item.get("company_type") or "") or "unknown",
                    str(item.get("funding_stage") or "") or None,
                    "catalog",
                    version,
                    0,
                    1,
                    str(item.get("reason") or ""),
                    now,
                    now,
                )
            )
        conn.executemany(
            """INSERT INTO companies
               (catalog_id, name, normalized_name, url, normalized_url, country, city, industry, company_type,
                funding_stage, source, batch, enabled, needs_review, review_reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                str(target.get("company_type") or "unknown"),
                str(target.get("funding_stage") or "") or None,
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
               (catalog_id, name, normalized_name, url, normalized_url, country, city, industry, company_type, funding_stage,
                source, batch, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
    company_type: str = "",
    funding_stage: str = "",
    needs_review: bool | None = None,
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
    if company_type:
        clauses.append("company_type = ?")
        params.append(company_type)
    if funding_stage:
        clauses.append("funding_stage = ?")
        params.append(funding_stage)
    if enabled is not None:
        clauses.append("enabled = ?")
        params.append(1 if enabled else 0)
    if needs_review is not None:
        clauses.append("needs_review = ?")
        params.append(1 if needs_review else 0)
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
    company_type: str = "",
    funding_stage: str = "",
    needs_review: bool | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    where, params = _build_where(
        country=country,
        city=city,
        industry=industry,
        enabled=enabled,
        source=source,
        search=search,
        company_type=company_type,
        funding_stage=funding_stage,
        needs_review=needs_review,
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


def _automatic_startup_rows(
    conn: sqlite3.Connection, countries: list[str] | None, excluded: list[str], cap: int
) -> list[dict[str, Any]]:
    where = ["source = 'catalog'", "company_type IN ('startup', 'scaleup')"]
    params: list[Any] = []
    if countries is not None:
        where.append(f"country IN ({','.join('?' * len(countries))})")
        params.extend(countries)
    if excluded:
        where.append(f"industry NOT IN ({','.join('?' * len(excluded))})")
        params.extend(excluded)
    sql = f"SELECT * FROM companies WHERE {' AND '.join(where)} ORDER BY country, normalized_name"  # noqa: S608
    counts: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for row in conn.execute(sql, params):
        country = row["country"]
        if counts.get(country, 0) < cap:
            result.append(dict(row))
            counts[country] = counts.get(country, 0) + 1
    return result


def candidate_companies(
    root: Path,
    *,
    countries: list[str] | None,
    excluded_industries: Iterable[str] = (),
    include_startups: bool = False,
    startup_cap: int = 100,
) -> list[dict[str, Any]]:
    """Enabled companies eligible for a hunt: gated by country and industry exclusion.

    `countries=None` means every country is allowed (a remote_global region is enabled);
    `countries=[]` means no region is enabled, so nothing matches. When a user target and
    a catalog row share the same (normalized_url, country), the user row wins — same
    override semantics as the old career_pages.yml custom-entry-wins rule.
    """
    if countries is not None and not countries:
        return []
    where = ["enabled = 1", "needs_review = 0"]
    params: list[Any] = []
    if countries is not None:
        where.append(f"country IN ({','.join('?' * len(countries))})")
        params.extend(countries)
    excluded = list(excluded_industries)
    if excluded:
        where.append(f"industry NOT IN ({','.join('?' * len(excluded))})")
        params.extend(excluded)
    # No ORDER BY: at 100k+ rows/country an unindexed `source, id` sort forces a temp
    # b-tree (measured ~170ms/call in scripts/benchmark_companies.py). The two-pass
    # dict build below gets the same "user overrides catalog" result from an unsorted
    # fetch — catalog rows populate first, user rows then overwrite by key.
    sql = f"SELECT * FROM companies WHERE {' AND '.join(where)}"  # noqa: S608
    with _conn(root) as conn:
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        if include_startups:
            rows.extend(_automatic_startup_rows(conn, countries, excluded, startup_cap))
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if row["source"] == "catalog":
            by_key.setdefault((row["normalized_url"], row["country"]), row)
    for row in rows:
        if row["source"] == "user":
            by_key[(row["normalized_url"], row["country"])] = row
    return list(by_key.values())


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
    company_type: str = "",
    funding_stage: str = "",
) -> int:
    where, params = _build_where(
        country=country,
        city=city,
        industry=industry,
        enabled=enabled,
        source=source,
        search=search,
        company_type=company_type,
        funding_stage=funding_stage,
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


def company_count(
    root: Path, *, enabled: bool | None = None, source: str = "", industry: str = "", needs_review: bool | None = None
) -> int:
    where, params = _build_where(enabled=enabled, source=source, industry=industry, needs_review=needs_review)
    with _conn(root) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM companies WHERE {where}", params).fetchone()[0]  # noqa: S608


def resolve_review(root: Path, company_id: int, *, industry: str = "", url: str = "") -> dict[str, Any]:
    """Apply fixes to a review-queue row, re-check the quality gates, clear the flag."""
    from job_hunter.filters.catalog import load_filter_catalog

    with _conn(root) as conn:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if row is None or not row["needs_review"]:
            return {"ok": False, "errors": ["No review row with that id."]}
        new_url = (url or row["url"]).strip()
        new_industry = (industry or row["industry"] or "").strip()
        errors = []
        if not new_url.startswith("https://"):
            errors.append("URL must be https.")
        if new_industry not in {item.id for item in load_filter_catalog().industries}:
            errors.append("Pick an industry from the taxonomy.")
        if errors:
            return {"ok": False, "errors": errors}
        conn.execute(
            """UPDATE companies SET url = ?, normalized_url = ?, industry = ?, needs_review = 0,
               review_reason = '', updated_at = ? WHERE id = ?""",
            (new_url, _normalize_url(new_url), new_industry, _now(), company_id),
        )
    return {"ok": True, "errors": []}


def seed_progress(root: Path, targets: list[dict[str, Any]], *, target_count: int = 1000) -> list[dict[str, Any]]:
    """Catalog coverage per hunt target ({country, city?}) vs the per-city growth goal."""
    results = []
    with _conn(root) as conn:
        for target in targets:
            country = str(target.get("country") or "")
            city = str(target.get("city") or "")
            if not country:
                continue  # remote_global targets have no coverage denominator
            where = "source = 'catalog' AND needs_review = 0 AND country = ?"
            params: list[Any] = [country]
            if city:
                where += " AND city = ?"
                params.append(city)
            count = conn.execute(f"SELECT COUNT(*) FROM companies WHERE {where}", params).fetchone()[0]  # noqa: S608
            results.append({"country": country, "city": city, "count": count, "target": target_count})
    return results
