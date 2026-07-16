"""Load the read-only filter taxonomy shipped in the package."""

from functools import lru_cache
from importlib import resources

from job_hunter.models import FilterCatalog


@lru_cache(maxsize=1)
def load_filter_catalog() -> FilterCatalog:
    raw = resources.files("job_hunter").joinpath("catalog", "filters.json").read_text(encoding="utf-8")
    return FilterCatalog.model_validate_json(raw)
