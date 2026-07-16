"""Repeatable microbenchmarks for the package-owned location subsystem."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _elapsed_ms(operation: Callable[[], Any], repetitions: int = 1) -> float:
    started = time.perf_counter()
    for _ in range(repetitions):
        operation()
    return (time.perf_counter() - started) * 1_000


def _isolated(code: str) -> dict[str, Any]:
    output = subprocess.check_output([sys.executable, "-c", code], text=True)  # noqa: S603
    return json.loads(output)


def main() -> None:
    cold = _isolated(
        "import json,time; s=time.perf_counter(); import job_hunter.locations; "
        "print(json.dumps({'milliseconds':(time.perf_counter()-s)*1000}))"
    )
    no_hint = _isolated(
        "import json,time; import job_hunter.locations as l; "
        "s=time.perf_counter(); l.canonicalize_runtime_location('Berlin'); "
        "elapsed=(time.perf_counter()-s)*1000; "
        "print(json.dumps({'milliseconds':elapsed,"
        "'city_files':l.cities.cache_info().currsize}))"
    )

    import job_hunter.locations as locations
    from job_hunter.catalog.loader import CompanyEntry
    from job_hunter.catalog.merge import company_matches_enabled_locations
    from job_hunter.models import Location, LocationScope
    from job_hunter.ux.web.api import DashAPI  # noqa: TID251 - benchmark payload boundary

    locations.cities.cache_clear()
    locations._city_index.cache_clear()
    first_cities = _elapsed_ms(lambda: locations.cities("DE"))
    repeated_cities = _elapsed_ms(lambda: locations.cities("DE"), 10_000)
    first_index = _elapsed_ms(lambda: locations.canonicalize_runtime_location("Berlin", "DE"))
    repeated_lookup = _elapsed_ms(lambda: locations.canonicalize_runtime_location("München", "DE"), 1_000)

    samples = ("Berlin, Germany", "München", "Stuttgart", "Remote Germany")
    canonicalization = _elapsed_ms(
        lambda: [locations.canonicalize_runtime_location(value, "DE") for value in samples],
        250,
    )
    berlin = locations.resolve_config_location("DE", "Berlin")
    munich = locations.resolve_config_location("DE", "Munich")
    allowed = [berlin, munich]
    jobs = (
        {"canonical_locations": [berlin.model_dump()]},
        {"canonical_locations": [munich.model_dump()]},
        {
            "canonical_locations": [
                Location(
                    country="DE", scope=LocationScope.CITY, city=locations._city_index("DE")["stuttgart"]
                ).model_dump()
            ]
        },
    )
    job_gate = _elapsed_ms(
        lambda: [locations.job_matches_enabled_locations(job, allowed) for job in jobs],
        1_000,
    )
    company = CompanyEntry(
        id="benchmark",
        name="Benchmark",
        career_url="https://example.com/careers",
        country_codes=["DE"],
        city_tags=["Berlin"],
        industry_ids=["software_it"],
        verified_at="2026-07-16",
    )
    company_gate = _elapsed_ms(lambda: company_matches_enabled_locations(company, allowed), 1_000)

    api = DashAPI(Path.cwd())
    countries_payload = json.dumps(api.get_location_countries(), separators=(",", ":")).encode()
    cities_payload = json.dumps(api.get_location_cities("DE"), separators=(",", ":")).encode()
    result = {
        "cold_import_ms": cold["milliseconds"],
        "global_no_hint": no_hint,
        "country_cache": {
            "first_cities_ms": first_cities,
            "repeated_10000_ms": repeated_cities,
            "first_index_lookup_ms": first_index,
            "repeated_lookup_1000_ms": repeated_lookup,
            "loaded_city_files": locations.cities.cache_info().currsize,
        },
        "canonicalize_1000_ms": canonicalization,
        "job_gate_3000_ms": job_gate,
        "company_gate_1000_ms": company_gate,
        "payload_bytes": {"countries": len(countries_payload), "cities_DE": len(cities_payload)},
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
