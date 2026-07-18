"""Import maintainer-provided startup CSV/JSONL into package company shards."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from job_hunter.companies.classification import classify_company
from job_hunter.config.reference_data import country_codes
from job_hunter.models import FundingStage

DATA_DIR = Path(__file__).parents[1] / "job_hunter" / "companies" / "data"
REQUIRED = {"name", "career_url", "country", "industry"}


def _read(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _industry_ids() -> dict[str, str]:
    from scripts.seed_companies import _industry_aliases

    return _industry_aliases()


def _normalize(row: dict[str, Any], line: int) -> dict[str, Any]:
    missing = REQUIRED - {key for key, value in row.items() if str(value or "").strip()}
    if missing:
        raise ValueError(f"line {line}: missing {', '.join(sorted(missing))}")
    url = str(row["career_url"]).strip()
    if urlparse(url).scheme != "https" or not urlparse(url).netloc:
        raise ValueError(f"line {line}: career_url must be https")
    country = str(row["country"]).strip().upper()
    if country not in country_codes():
        raise ValueError(f"line {line}: unknown country {country}")
    industry = _industry_ids().get(str(row["industry"]).strip().casefold())
    if not industry:
        raise ValueError(f"line {line}: industry does not map to canonical taxonomy")
    stage = str(row.get("funding_stage") or "").strip()
    if stage:
        FundingStage(stage)
    headcount = int(row["headcount"]) if str(row.get("headcount") or "").strip() else None
    company_type = classify_company(
        company_type=str(row.get("company_type") or "").strip(),
        funding_stage=stage,
        status=str(row.get("status") or "").strip(),
        headcount=headcount,
        ecosystem=str(row.get("ecosystem") or "").strip(),
    )
    result = {
        "id": str(row.get("id") or str(row["name"]).casefold().replace(" ", "_")),
        "name": str(row["name"]).strip(),
        "url": url,
        "industry": industry,
        "company_type": company_type.value,
    }
    if stage:
        result["funding_stage"] = stage
    return {"country": country, **result}


def import_file(path: Path) -> int:
    incoming = [_normalize(row, i) for i, row in enumerate(_read(path), 2)]
    by_country: dict[str, list[dict[str, Any]]] = {}
    for row in incoming:
        by_country.setdefault(row.pop("country"), []).append(row)
    for country, additions in by_country.items():
        shard = DATA_DIR / f"{country}.jsonl"
        existing = [json.loads(line) for line in shard.read_text(encoding="utf-8").splitlines() if line.strip()]
        by_url = {str(row["url"]).strip().rstrip("/").casefold(): row for row in existing}
        for row in additions:
            by_url[str(row["url"]).strip().rstrip("/").casefold()] = row
        ordered = sorted(by_url.values(), key=lambda row: (str(row["name"]).casefold(), str(row["id"])))
        shard.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in ordered), encoding="utf-8")
    # single shared manifest writer — keeps review counts and the version digest consistent
    from scripts.seed_companies import _write_manifest

    _write_manifest(DATA_DIR)
    return len(incoming)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(f"Imported {import_file(args.input)} companies")


if __name__ == "__main__":
    main()
