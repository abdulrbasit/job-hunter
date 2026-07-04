"""Search and career-page provider strategies.

Re-exports all public symbols from this package's submodules so that
existing import sites require no changes.
"""

from __future__ import annotations

import logging

import requests  # noqa: F401 — exposed so tests can patch search.requests.get/post

from job_hunter.sources.search._constants import (
    BRAVE_SUPPORTED_COUNTRIES,
    BRAVE_URL,
    EXA_URL,
    JOB_HINTS,
    TAVILY_URL,
    TRACKING_QUERY_KEYS,
    TRACKING_QUERY_PREFIXES,
    USER_AGENT,
)
from job_hunter.sources.search._result import (
    SearchResult,
    normalize_web_results,
)
from job_hunter.sources.search._url_utils import (
    _location_match,
    _looks_like_job_url,
    _text,
    _with_scheme,
    canonicalize_url,
)
from job_hunter.sources.search.ats_discovery import (
    _ats_search_queries,
    _discover_region,
    _enrich_ats_discovery_job,
    discover_ats_jobs_by_search,
)
from job_hunter.sources.search.discovery import (
    discover_company_homepage,
    search_career_urls,
)
from job_hunter.sources.search.fetchers import (
    extract_jobs_from_html,
    fetch_playwright_career_jobs,
    fetch_static_career_jobs,
)
from job_hunter.sources.search.providers import (
    BraveProvider,
    ExaProvider,
    SearchProvider,
    SearxngProvider,
    TavilyProvider,
    _timeout,
)
from job_hunter.sources.search.router import (
    _PROVIDER_STATE,
    ProviderSearchRouter,
    ProviderState,
    SearchRouter,
    SearchRouterHealth,
    _provider_failure_count,
    _reset_provider_failure,
    all_providers_exhausted,
    search_web,
    set_run_disabled,
)

__all__ = [
    "_PROVIDER_STATE",
    "_ats_search_queries",
    "_discover_region",
    "_enrich_ats_discovery_job",
    "_provider_failure_count",
    "_reset_provider_failure",
    "_timeout",
    "logger",
    "BRAVE_SUPPORTED_COUNTRIES",
    "BRAVE_URL",
    "EXA_URL",
    "JOB_HINTS",
    "TAVILY_URL",
    "TRACKING_QUERY_KEYS",
    "TRACKING_QUERY_PREFIXES",
    "USER_AGENT",
    "SearchResult",
    "SearchRouterHealth",
    "ProviderState",
    "normalize_web_results",
    "_location_match",
    "_looks_like_job_url",
    "_text",
    "_with_scheme",
    "canonicalize_url",
    "discover_ats_jobs_by_search",
    "discover_company_homepage",
    "search_career_urls",
    "extract_jobs_from_html",
    "fetch_playwright_career_jobs",
    "fetch_static_career_jobs",
    "BraveProvider",
    "ExaProvider",
    "SearchProvider",
    "SearxngProvider",
    "TavilyProvider",
    "ProviderSearchRouter",
    "SearchRouter",
    "all_providers_exhausted",
    "search_web",
    "set_run_disabled",
]

logger = logging.getLogger(__name__)
