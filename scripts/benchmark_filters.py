"""Repeatable microbenchmarks for package-owned filter binding and matching."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any


def _elapsed_ms(operation: Callable[[], Any], repetitions: int) -> float:
    started = time.perf_counter()
    for _ in range(repetitions):
        operation()
    return (time.perf_counter() - started) * 1_000


def _cold_import_ms() -> float:
    code = (
        "import json,time; s=time.perf_counter(); import job_hunter.filters; "
        "print(json.dumps((time.perf_counter()-s)*1000))"
    )
    output = subprocess.check_output([sys.executable, "-c", code], text=True)  # noqa: S603
    return float(json.loads(output))


def main() -> None:
    from job_hunter.filters import FilterSet

    config = {
        "filters": {
            "excluded_companies": ["Acme GmbH", "Example Holdings", "Legacy Systems"],
            "excluded_industries": ["finance", "manufacturing", "retail_ecommerce"],
            "hunt_languages": ["en", "de"],
        }
    }
    filters = FilterSet.from_config(config)
    result = {
        "cold_import_ms": _cold_import_ms(),
        "construct_1000_ms": _elapsed_ms(lambda: FilterSet.from_config(config), 1_000),
        "exact_100000_ms": _elapsed_ms(lambda: filters.matches("hunt_languages", "en"), 100_000),
        "company_100000_ms": _elapsed_ms(lambda: filters.matches("excluded_companies", "ACME GmbH (Germany)"), 100_000),
        "industry_100000_ms": _elapsed_ms(
            lambda: filters.matches("excluded_industries", "Financial Services"), 100_000
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
