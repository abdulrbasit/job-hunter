"""Build the vendored per-country GeoNames city snapshot.

Input archives are downloaded manually from the official GeoNames dump. The
application never calls the network at runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def _rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        name = next(item for item in archive.namelist() if item.endswith(".txt"))
        return [line.decode("utf-8").rstrip("\n").split("\t") for line in archive.open(name)]


def _city(row: list[str]) -> dict[str, object]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in (row[1], row[2], *(row[3].split(",") if row[3] else [])):
        value = value.strip()
        key = value.casefold()
        if not value or len(value) > 80 or key in seen or "://" in value:
            continue
        seen.add(key)
        aliases.append(value)
        if len(aliases) == 100:
            break
    return {
        "id": f"geonames:{row[0]}",
        "name": row[1],
        "aliases": aliases,
        "population": int(row[14] or 0),
    }


def build(global_archive: Path, germany_archive: Path, output: Path) -> None:
    by_country: dict[str, dict[str, dict[str, object]]] = {}
    for row in _rows(global_archive):
        by_country.setdefault(row[8], {})[row[0]] = _city(row)
    by_country["DE"] = {row[0]: _city(row) for row in _rows(germany_archive) if row[8] == "DE"}

    cities_dir = output / "cities"
    cities_dir.mkdir(parents=True, exist_ok=True)
    for country, cities in sorted(by_country.items()):
        ordered = sorted(cities.values(), key=lambda item: (-int(item["population"]), str(item["name"])))
        (cities_dir / f"{country}.json").write_text(
            json.dumps(ordered, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )

    manifest = {
        "version": 1,
        "source": "GeoNames cities15000; cities500 for Germany",
        "license": "CC BY 4.0",
        "source_url": "https://download.geonames.org/export/dump/",
        "archives": {
            global_archive.name: hashlib.sha256(global_archive.read_bytes()).hexdigest(),
            germany_archive.name: hashlib.sha256(germany_archive.read_bytes()).hexdigest(),
        },
        "countries_with_cities": len(by_country),
        "city_count": sum(len(cities) for cities in by_country.values()),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("global_archive", type=Path)
    parser.add_argument("germany_archive", type=Path)
    parser.add_argument("output", type=Path, help="Package directory, normally job_hunter/locations/data")
    args = parser.parse_args()
    build(args.global_archive, args.germany_archive, args.output)


if __name__ == "__main__":
    main()
