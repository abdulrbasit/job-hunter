"""Maintainer-curated list provider — CSV/JSONL drops in scripts/seed_data/.

The home for hand-curated facts from largest-employer and chamber-of-commerce
material (facts are not copyrightable; curation is ours), and the drop point the
existing startup lists can flow through. Columns: name, url (or career_url),
country, and optionally city, industry, company_type, funding_stage, headcount,
status, ecosystem.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

NAME = "manual"
DATA_DIR = Path(__file__).resolve().parents[1] / "seed_data"


def _read(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return []


def fetch(country: str, city: str | None = None) -> list[dict]:
    code = country.upper()
    rows: list[dict] = []
    if not DATA_DIR.is_dir():
        return rows
    for path in sorted(DATA_DIR.iterdir()):
        for row in _read(path):
            if str(row.get("country") or "").strip().upper() != code:
                continue
            rows.append(
                {
                    "name": str(row.get("name") or "").strip(),
                    "url": str(row.get("url") or row.get("career_url") or "").strip(),
                    "city": str(row.get("city") or "").strip(),
                    "industry_hint": str(row.get("industry") or "").strip(),
                    "company_type": str(row.get("company_type") or "").strip(),
                    "funding_stage": str(row.get("funding_stage") or "").strip(),
                    "headcount": row.get("headcount"),
                    "status": str(row.get("status") or "").strip(),
                    "ecosystem": str(row.get("ecosystem") or "").strip(),
                }
            )
    return rows
