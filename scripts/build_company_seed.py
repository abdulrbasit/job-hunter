"""Build the per-country company seed shards from job_hunter/catalog/companies.json.

One-shot converter: the bundled catalog (one row per company, multiple country_codes)
becomes one JSONL shard per country (one row per company x country), because the
runtime store's uniqueness key is (normalized_url, country) — a multi-country company
must be sharded to keep every country queryable without a cross-shard scan.

Usage: uv run python scripts/build_company_seed.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "job_hunter" / "companies" / "data"


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def build() -> None:
    # Loads through job_hunter.catalog.loader — same pydantic validation (https-only,
    # known country/industry ids, unique id/url) the runtime already enforces on this file.
    from job_hunter.catalog.loader import load_companies

    by_country: dict[str, list[dict[str, object]]] = {}
    for company in load_companies():
        industry = (company.industry_ids or ["other"])[0]
        for country in company.country_codes:
            by_country.setdefault(country, []).append(
                {
                    "id": company.id,
                    "name": company.name,
                    "url": company.career_url,
                    "industry": industry,
                }
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_shard in OUTPUT_DIR.glob("*.jsonl"):
        old_shard.unlink()

    manifest_files: dict[str, int] = {}
    hasher = hashlib.sha256()
    for country in sorted(by_country):
        rows = sorted(by_country[country], key=lambda r: r["id"])
        seen_urls: set[str] = set()
        for row in rows:
            normalized = _normalize_url(row["url"])
            if normalized in seen_urls:
                raise ValueError(f"{country}: duplicate career_url within one country shard: {row['url']}")
            seen_urls.add(normalized)
        lines = "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n"
        (OUTPUT_DIR / f"{country}.jsonl").write_text(lines, encoding="utf-8")
        hasher.update(lines.encode("utf-8"))
        manifest_files[country] = len(rows)

    manifest = {
        "version": hasher.hexdigest()[:12],
        "files": manifest_files,
        "total": sum(manifest_files.values()),
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(manifest_files)} shards, {manifest['total']} rows, version {manifest['version']}")


if __name__ == "__main__":
    build()
