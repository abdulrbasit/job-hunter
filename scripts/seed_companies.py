"""Maintainer seeding pipeline: grow package-owned company shards from pluggable providers.

Writes job_hunter/companies/data/<CC>.jsonl (shipped in the wheel) and a review
queue at data/review/<CC>.jsonl for rows failing the quality gates (name + https
URL + known country + mapped industry). Never touches a user workspace — end
users receive grown data via package updates and import it with the dashboard's
Grow button.

Usage:
    uv run python scripts/seed_companies.py DE [--city Munich]
    uv run python scripts/seed_companies.py --rotate-daily   # today's bucket of all countries
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root: scripts.* imports under direct run

from job_hunter.companies.classification import classify_company
from job_hunter.config.reference_data import country_codes
from job_hunter.filters.catalog import load_filter_catalog
from job_hunter.locations import city_by_name_exact, countries
from job_hunter.models import FundingStage
from scripts.seed_providers import iter_providers

DATA_DIR = Path(__file__).resolve().parents[1] / "job_hunter" / "companies" / "data"

# Keyword fallback when the provider's industry hint has no direct taxonomy alias.
# Checked in order; first hit wins. Matched against the casefolded hint, then the name.
_KEYWORD_INDUSTRIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("finance", ("bank", "insurance", "asset management", "payment", "invest")),
    ("biotech_pharma", ("pharma", "biotech", "life science", "drug")),
    ("healthcare", ("hospital", "clinic", "health", "medical")),
    ("automotive", ("automotive", "automobile", "car manufactur", "vehicle")),
    ("energy", ("energy", "electric utility", "oil", "gas", "renewable", "power company")),
    ("telecommunications", ("telecom",)),
    ("aerospace_defense", ("aerospace", "aviation", "airline", "defense", "defence")),
    ("transportation_logistics", ("logistic", "railway", "shipping", "transport", "freight")),
    ("retail_ecommerce", ("retail", "e-commerce", "ecommerce", "supermarket", "grocery")),
    ("media_entertainment", ("media", "broadcast", "publish", "game", "entertainment", "television")),
    ("manufacturing", ("manufactur", "industrial", "machinery", "chemical", "steel", "electronics")),
    ("real_estate", ("real estate", "property")),
    ("hospitality_travel", ("hotel", "travel", "tourism", "restaurant")),
    ("education", ("education", "university", "school")),
    ("agriculture", ("agricultur", "farming", "food producer")),
    ("consulting", ("consult", "accounting", "audit")),
    ("software_it", ("software", "information technology", "internet", "cloud", "computer", "tech company")),
)


@cache
def _industry_aliases() -> dict[str, str]:
    result: dict[str, str] = {}
    for item in load_filter_catalog().industries:
        for value in (item.id, item.label, *item.aliases):
            result[value.strip().casefold()] = item.id
    return result


def _map_industry(hint: str, name: str) -> str:
    needle = hint.strip().casefold()
    if needle:
        alias = _industry_aliases().get(needle)
        if alias:
            return alias
    for industry, keywords in _KEYWORD_INDUSTRIES:
        for text in (needle, name.casefold()):
            if text and any(keyword in text for keyword in keywords):
                return industry
    return ""


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").casefold()


def _normalize_name(name: str) -> str:
    return name.strip().casefold()


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name.strip().casefold()).strip("_")


def _load_shard(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_shard(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: (str(row["name"]).casefold(), str(row.get("id", ""))))
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in ordered), encoding="utf-8")


def _write_manifest() -> None:
    files = sorted(DATA_DIR.glob("[A-Z][A-Z].jsonl"))
    review_files = sorted((DATA_DIR / "review").glob("[A-Z][A-Z].jsonl")) if (DATA_DIR / "review").is_dir() else []

    def count(path: Path) -> int:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    payload = {
        "files": {path.stem: count(path) for path in files},
        "review": {path.stem: count(path) for path in review_files},
        "total": sum(count(path) for path in files),
        "version": hashlib.sha256(b"".join(path.read_bytes() for path in [*files, *review_files])).hexdigest()[:12],
    }
    (DATA_DIR / "manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fetch_all(country: str, city: str | None) -> list[dict]:
    rows: list[dict] = []
    for provider in iter_providers():
        try:
            fetched = provider.fetch(country, city)
        except Exception as exc:  # noqa: BLE001 — one flaky provider must not sink the run
            print(f"[seed] {provider.NAME} failed for {country}: {exc}")
            continue
        rows.extend({**row, "_src": provider.NAME} for row in fetched)
    return rows


def _gate(row: dict, country: str, batch: str) -> tuple[dict | None, dict | None]:
    """Return (accepted, review) — exactly one is set, or neither for unusable rows."""
    name = str(row.get("name") or "").strip()
    url = str(row.get("url") or "").strip()
    if not name or not url:
        return None, None
    parsed = urlparse(url)
    industry = _map_industry(str(row.get("industry_hint") or ""), name)
    city_name = str(row.get("city") or "").strip()
    resolved_city = city_by_name_exact(country, city_name) if city_name else None

    result: dict = {"id": _slug(name), "name": name, "url": url, "industry": industry}
    if resolved_city is not None:
        result["city"] = resolved_city.id
    stage = str(row.get("funding_stage") or "").strip()
    if stage:
        FundingStage(stage)
        result["funding_stage"] = stage
    headcount = row.get("headcount")
    company_type = classify_company(
        company_type=str(row.get("company_type") or "").strip(),
        funding_stage=stage,
        status=str(row.get("status") or "").strip(),
        headcount=int(headcount) if str(headcount or "").strip() else None,
        ecosystem=str(row.get("ecosystem") or "").strip(),
    )
    if company_type.value != "unknown":
        result["company_type"] = company_type.value
    result["src"] = str(row.get("_src") or "")
    result["batch"] = batch

    reasons = []
    if parsed.scheme != "https" or not parsed.netloc:
        reasons.append("url_not_https")
    if not industry:
        reasons.append("industry_unmapped")
        result.pop("industry")
        result["industry_hint"] = str(row.get("industry_hint") or "")
    if reasons:
        return None, {**result, "reason": ",".join(reasons)}
    return result, None


def seed_country(country: str, city: str | None = None) -> dict:
    """Fetch, gate, dedup, and merge one country's rows into its shard + review shard."""
    code = country.upper()
    batch = datetime.now(UTC).date().isoformat()
    fetched = _fetch_all(code, city)
    city_id = ""
    if city:
        resolved = city_by_name_exact(code, city)
        city_id = resolved.id if resolved else ""

    shard_path = DATA_DIR / f"{code}.jsonl"
    review_path = DATA_DIR / "review" / f"{code}.jsonl"
    shard = _load_shard(shard_path)
    review = _load_shard(review_path)
    shard_urls = {_normalize_url(row["url"]) for row in shard}
    shard_names = {_normalize_name(row["name"]) for row in shard}
    review_urls = {_normalize_url(row["url"]) for row in review}

    accepted_count = review_count = 0
    for row in fetched:
        accepted, needs_review = _gate(row, code, batch)
        candidate = accepted or needs_review
        if candidate is None:
            continue
        if city_id and candidate.get("city") != city_id:
            continue
        url_key = _normalize_url(candidate["url"])
        name_key = _normalize_name(candidate["name"])
        if accepted is not None:
            if url_key in shard_urls or name_key in shard_names:
                continue
            shard.append(accepted)
            shard_urls.add(url_key)
            shard_names.add(name_key)
            accepted_count += 1
        else:
            if url_key in shard_urls or url_key in review_urls:
                continue
            review.append(needs_review)
            review_urls.add(url_key)
            review_count += 1

    # rows that made it into the main shard leave the review queue
    review = [row for row in review if _normalize_url(row["url"]) not in shard_urls]

    _write_shard(shard_path, shard)
    _write_shard(review_path, review)
    _write_manifest()
    return {"fetched": len(fetched), "accepted": accepted_count, "review": review_count}


def rotation_countries(day: date | None = None) -> list[str]:
    """Deterministic daily bucket over the full package country universe (~1/7 per day)."""
    codes = sorted(c["code"] for c in countries())
    bucket = (day or date.today()).toordinal() % 7
    return [code for index, code in enumerate(codes) if index % 7 == bucket]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("countries", nargs="*", help="ISO alpha-2 country codes")
    parser.add_argument("--city", default="", help="grow one city only (canonical name)")
    parser.add_argument("--rotate-daily", action="store_true", help="seed today's rotation bucket of all countries")
    args = parser.parse_args()

    if args.rotate_daily:
        targets = rotation_countries()
    else:
        targets = [code.upper() for code in args.countries]
        unknown = [code for code in targets if code not in country_codes()]
        if unknown:
            parser.error(f"unknown country code(s): {', '.join(unknown)}")
    if not targets:
        parser.error("give country codes or --rotate-daily")

    for code in targets:
        result = seed_country(code, city=args.city or None)
        print(f"[seed] {code}: fetched={result['fetched']} accepted={result['accepted']} review={result['review']}")


if __name__ == "__main__":
    main()
