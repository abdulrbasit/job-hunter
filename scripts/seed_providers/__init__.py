"""Pluggable company-seed providers for the maintainer seeding pipeline.

Each provider is one module in this package exposing:
- ``NAME: str`` — provenance tag written into seed rows.
- ``fetch(country: str, city: str | None = None) -> list[dict]`` — raw candidate rows
  ``{name, url, city?, industry_hint?, company_type?, funding_stage?, headcount?, status?, ecosystem?}``.

Adding a provider = dropping a module here; nothing else changes.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator
from types import ModuleType


def iter_providers() -> Iterator[ModuleType]:
    for info in pkgutil.iter_modules(__path__):
        if not info.name.startswith("_"):
            yield importlib.import_module(f"{__name__}.{info.name}")
