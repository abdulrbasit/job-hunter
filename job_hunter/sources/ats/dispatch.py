from __future__ import annotations

import logging

from job_hunter.models import SearchParams
from job_hunter.sources.ats._base import make_ats_source
from job_hunter.sources.ats.ashby import fetch_ashby_jobs
from job_hunter.sources.ats.bamboohr import fetch_bamboohr_jobs
from job_hunter.sources.ats.breezy import fetch_breezy_jobs
from job_hunter.sources.ats.greenhouse import fetch_greenhouse_jobs
from job_hunter.sources.ats.hibob import fetch_hibob_jobs
from job_hunter.sources.ats.lever import fetch_lever_jobs
from job_hunter.sources.ats.personio import fetch_personio_jobs
from job_hunter.sources.ats.recruitee import fetch_recruitee_jobs
from job_hunter.sources.ats.smartrecruiters import fetch_smartrecruiters_jobs
from job_hunter.sources.ats.teamtailor import fetch_teamtailor_jobs
from job_hunter.sources.ats.workable import fetch_workable_jobs
from job_hunter.sources.ats.workday import fetch_workday_jobs
from job_hunter.sources.ats_urls import detect_ats

logger = logging.getLogger(__name__)

_ADAPTERS = {
    "ashby": make_ats_source("ashby", fetch_ashby_jobs),
    "bamboohr": make_ats_source("bamboohr", fetch_bamboohr_jobs),
    "breezy": make_ats_source("breezy", fetch_breezy_jobs),
    "greenhouse": make_ats_source("greenhouse", fetch_greenhouse_jobs),
    "hibob": make_ats_source("hibob", fetch_hibob_jobs),
    "lever": make_ats_source("lever", fetch_lever_jobs),
    "personio": make_ats_source("personio", fetch_personio_jobs),
    "recruitee": make_ats_source("recruitee", fetch_recruitee_jobs),
    "smartrecruiters": make_ats_source("smartrecruiters", fetch_smartrecruiters_jobs),
    "teamtailor": make_ats_source("teamtailor", fetch_teamtailor_jobs),
    "workable": make_ats_source("workable", fetch_workable_jobs),
    "workday": make_ats_source("workday", fetch_workday_jobs),
}


def fetch_ats_jobs(
    company: dict,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict] | None:
    """
    Fetch jobs via direct ATS API for a given company.
    Returns None if the career_url is not a recognised ATS (caller should fall back to Brave).
    Returns [] if the ATS was reached but no matching jobs were found.
    """
    detected = detect_ats(company["career_url"])
    if detected is None:
        return None

    ats_name, slug = detected
    adapter_cls = _ADAPTERS.get(ats_name)
    if adapter_cls is None:
        logger.debug(f"[ats] No fetcher for {ats_name}, falling back to Brave")
        return None

    logger.info(f"[ats] {company['name']} -> {ats_name.capitalize()} (slug={slug})")
    params = SearchParams(
        region_key=str(company.get("region") or ""),
        country=str(company.get("country") or ""),
        location=location_filter,
        search_lang=str(company.get("search_lang") or ""),
        job_titles=title_filters,
        excluded_title_terms=excluded_title_terms or [],
    )
    adapter = adapter_cls(slug, company["name"], excluded_title_terms)
    return [posting.to_dict() for posting in adapter.fetch(params)]
