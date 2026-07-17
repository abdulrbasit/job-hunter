"""Bundled common job titles, used only to back an autocomplete suggestion list.

Free text is always accepted regardless of this list — see job_hunter/core/experience.py
for the loader pattern this mirrors.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from job_hunter.models import JobTitleCatalog


@lru_cache(maxsize=1)
def load_job_titles() -> list[str]:
    raw = resources.files("job_hunter").joinpath("catalog", "job_titles.json").read_text(encoding="utf-8")
    return JobTitleCatalog.model_validate_json(raw).titles
