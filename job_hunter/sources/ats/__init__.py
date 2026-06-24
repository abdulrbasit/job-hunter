"""ATS scrapers package with lazy compatibility exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

import requests  # noqa: F401 - kept for legacy tests/callers that patch ats.requests

_EXPORT_MODULES = {
    "detect_ats": "job_hunter.sources.ats_urls",
    "fetch_ats_jobs": "job_hunter.sources.ats.dispatch",
    "_FETCH_FNS": "job_hunter.sources.ats.dispatch",
    "fetch_greenhouse_jobs": "job_hunter.sources.ats.greenhouse",
    "fetch_lever_jobs": "job_hunter.sources.ats.lever",
    "fetch_bamboohr_jobs": "job_hunter.sources.ats.bamboohr",
    "fetch_smartrecruiters_jobs": "job_hunter.sources.ats.smartrecruiters",
    "fetch_workable_jobs": "job_hunter.sources.ats.workable",
    "fetch_ashby_jobs": "job_hunter.sources.ats.ashby",
    "fetch_hibob_jobs": "job_hunter.sources.ats.hibob",
    "fetch_personio_jobs": "job_hunter.sources.ats.personio",
    "fetch_recruitee_jobs": "job_hunter.sources.ats.recruitee",
    "fetch_teamtailor_jobs": "job_hunter.sources.ats.teamtailor",
    "fetch_workday_jobs": "job_hunter.sources.ats.workday",
}

__all__ = [
    "detect_ats",
    "fetch_ats_jobs",
    "_FETCH_FNS",
    "fetch_greenhouse_jobs",
    "fetch_lever_jobs",
    "fetch_bamboohr_jobs",
    "fetch_smartrecruiters_jobs",
    "fetch_workable_jobs",
    "fetch_ashby_jobs",
    "fetch_hibob_jobs",
    "fetch_personio_jobs",
    "fetch_recruitee_jobs",
    "fetch_teamtailor_jobs",
    "fetch_workday_jobs",
]


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
