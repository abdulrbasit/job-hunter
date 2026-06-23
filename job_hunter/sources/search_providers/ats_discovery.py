"""ATS discovery via search: _ATS_DISCOVERY_SITES, discover_ats_jobs_by_search, location helpers."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import requests

from job_hunter.constants import ATS_DISCOVERY_API_TIMEOUT
from job_hunter.core.config import load_api_config
from job_hunter.core.utils import location_matches, title_matches
from job_hunter.sources.ats_urls import ats_discovery_sites
from job_hunter.sources.search_providers._result import SearchResult
from job_hunter.sources.search_providers._url_utils import canonicalize_url
from job_hunter.sources.search_providers.router import (
    ProviderSearchRouter,
    _provider_order,
    _search_cfg,
    all_providers_exhausted,
)

logger = logging.getLogger(__name__)

_ATS_DISCOVERY_SITES = ats_discovery_sites()


def _site_queries(site_query: str) -> list[str]:
    """Split grouped site queries into simple engine-friendly query fragments."""
    return [part.strip(" ()") for part in site_query.split(" OR ") if part.strip(" ()")]


def _ats_search_queries(site_query: str, title: str, location: str) -> list[str]:
    queries: list[str] = []
    for site in _site_queries(site_query):
        if location:
            queries.append(f'{site} "{title}" "{location}"')
        queries.append(f'{site} "{title}"')
    return queries


def _passes_ats_discovery_shape(url: str, source: str) -> bool:
    _, host_pattern, path_pattern = _ATS_DISCOVERY_SITES[source]
    parsed = urlparse(url)
    return (
        re.search(host_pattern, parsed.netloc, re.IGNORECASE) is not None
        and re.search(path_pattern, parsed.path, re.IGNORECASE) is not None
    )


def _company_from_ats_url(url: str, source: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if source in {"greenhouse", "lever", "ashby", "smartrecruiters", "workable"} and parts:
        return parts[0].replace("-", " ").replace("_", " ").strip().title()
    if source == "personio":
        if parsed.netloc.endswith(".jobs.personio.de"):
            return parsed.netloc.split(".jobs.personio.de", 1)[0].replace("-", " ").title()
        if parts and parts[0] != "job":
            return parts[0].replace("-", " ").title()
    if source == "recruitee":
        return parsed.netloc.split(".recruitee.com", 1)[0].replace("-", " ").title()
    if source == "hibob":
        return parsed.netloc.split(".careers.hibob.com", 1)[0].replace("-", " ").title()
    if source == "teamtailor":
        return parsed.netloc.split(".teamtailor.com", 1)[0].replace("-", " ").title()
    if source == "breezy":
        return parsed.netloc.split(".breezy.hr", 1)[0].replace("-", " ").title()
    if source == "workday" and parsed.netloc:
        return parsed.netloc.split(".", 1)[0].replace("-", " ").title()
    return ""


_ATS_LOCATION_VERIFIABLE = {
    "lever",
    "greenhouse",
    "ashby",
    "smartrecruiters",
    "workable",
    "recruitee",
}


def _verify_ats_location(url: str, source: str, location_filter: str) -> bool:
    """Return True if the ATS posting's location matches location_filter, or if unknown."""
    parts = urlparse(url).path.strip("/").split("/")
    try:
        if source == "lever":
            if len(parts) < 2:
                return True
            slug, job_id = parts[0], parts[1]
            resp = requests.get(
                f"https://api.lever.co/v0/postings/{slug}/{job_id}",
                timeout=ATS_DISCOVERY_API_TIMEOUT,
            )
            if not resp.ok:
                return True
            categories = resp.json().get("categories", {})
            primary = categories.get("location", "")
            all_locs = list(categories.get("allLocations") or ([primary] if primary else []))
            if not all_locs:
                return True
            return any(location_matches(loc, location_filter) for loc in all_locs)

        elif source == "greenhouse":
            if len(parts) < 3:
                return False  # not a valid JD URL; valid paths always have ≥3 parts
            slug, job_id = parts[0], parts[2]
            resp = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}",
                timeout=ATS_DISCOVERY_API_TIMEOUT,
            )
            if not resp.ok:
                return True
            location = resp.json().get("location", {}).get("name", "")
            return not location or location_matches(location, location_filter)

        elif source == "ashby":
            if len(parts) < 2:
                return True
            slug, job_id = parts[0], parts[1]
            resp = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}/job-posting/{job_id}",
                timeout=ATS_DISCOVERY_API_TIMEOUT,
            )
            if not resp.ok:
                return True
            location = resp.json().get("jobPosting", {}).get("locationName", "")
            return not location or location_matches(location, location_filter)

        elif source == "smartrecruiters":
            if len(parts) < 2:
                return True
            slug, posting_id = parts[0], parts[1]
            resp = requests.get(
                f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}",
                timeout=ATS_DISCOVERY_API_TIMEOUT,
            )
            if not resp.ok:
                return True
            loc = resp.json().get("location", {})
            city = loc.get("city", "")
            country = loc.get("country", "")
            location_str = ", ".join(filter(None, [city, country]))
            return (
                not location_str
                or location_matches(city, location_filter)
                or location_matches(location_str, location_filter)
            )

        elif source == "workable":
            if len(parts) < 3:
                return True
            slug, shortcode = parts[0], parts[2]
            resp = requests.get(
                f"https://apply.workable.com/api/v3/accounts/{slug}/jobs/{shortcode}",
                timeout=ATS_DISCOVERY_API_TIMEOUT,
            )
            if not resp.ok:
                return True
            location = resp.json().get("location", {}).get("location", "")
            return not location or location_matches(location, location_filter)

        elif source == "recruitee":
            parsed = urlparse(url)
            subdomain = parsed.netloc.split(".recruitee.com", 1)[0]
            slug = parsed.path.strip("/").split("/")[-1]
            if not subdomain or not slug:
                return True
            resp = requests.get(
                f"https://{subdomain}.recruitee.com/api/offers/{slug}",
                timeout=ATS_DISCOVERY_API_TIMEOUT,
            )
            if not resp.ok:
                return True
            offer = resp.json().get("offer", {})
            city = offer.get("city", "")
            location = offer.get("location", "")
            return (
                not (city or location)
                or location_matches(city, location_filter)
                or location_matches(location, location_filter)
            )

    except Exception as e:
        logger.debug("[ats_discovery] filter skipped: %s", e)
    return True


def _enrich_ats_discovery_job(url: str) -> dict | None:
    try:
        from job_hunter.sources.jd_fetcher import fetch_jd

        return fetch_jd(url, use_llm=False)
    except Exception as exc:
        logger.debug("[search-discovery] ATS enrichment failed for %s: %s", url, exc)
        return None


def _process_ats_result(
    result: SearchResult,
    source: str,
    query: str,
    location: str,
    title_filters: list[str],
    excluded_title_terms: list[str],
    seen: set[str],
    jobs: list[dict],
    *,
    log_skips: bool = False,
) -> None:
    """Enrich, filter, and append a single search result to jobs (mutates seen and jobs)."""
    if not _passes_ats_discovery_shape(result.url, source):
        return
    canonical = canonicalize_url(result.url)
    if canonical in seen:
        return
    seen.add(canonical)
    enriched = _enrich_ats_discovery_job(result.url)
    job_title = enriched.get("title", "") if enriched else result.title
    if not title_matches(job_title, title_filters, excluded_title_terms):
        return
    enriched_location = str((enriched or {}).get("location") or "")
    if enriched_location and not location_matches(enriched_location, location):
        if log_skips:
            logger.debug(
                "[search-discovery] %s location mismatch, skipping: %s",
                source,
                result.url,
            )
        return
    if (
        not enriched_location
        and source in _ATS_LOCATION_VERIFIABLE
        and not _verify_ats_location(result.url, source, location)
    ):
        if log_skips:
            logger.debug(
                "[search-discovery] %s location mismatch, skipping: %s",
                source,
                result.url,
            )
        return
    jobs.append(
        {
            "title": enriched.get("title", job_title) if enriched else job_title,
            "company": (enriched or {}).get("company") or _company_from_ats_url(result.url, source),
            "location": enriched_location or location,
            "url": result.url,
            "posted": (enriched or {}).get("posted", ""),
            "snippet": (enriched or {}).get("snippet", result.description),
            "source": (
                f"{result.source} ATS discovery: {source} API"
                if enriched
                else f"{result.source} ATS discovery: {source}"
            ),
            "query": query,
        }
    )


def _discover_region(
    region_name: str,
    region_config: dict,
    title_filters: list[str],
    excluded_title_terms: list[str],
    sources: list[str],
    router: object,
    *,
    max_results_per_query: int = 10,
    max_queries_per_region: int = 0,
    ats_detail_timeout: int = ATS_DISCOVERY_API_TIMEOUT,
) -> list[dict]:
    """Run ATS discovery for a single region. Used by tests and discover_ats_jobs_by_search."""
    location = region_config.get("location") or region_name
    jobs: list[dict] = []
    seen: set[str] = set()
    region_queries = 0

    for title in title_filters:
        for source in sources:
            if source not in _ATS_DISCOVERY_SITES:
                continue
            if max_queries_per_region > 0 and region_queries >= max_queries_per_region:
                break
            site_query, _, _ = _ATS_DISCOVERY_SITES[source]
            for query in _ats_search_queries(site_query, title, location):
                if max_queries_per_region > 0 and region_queries >= max_queries_per_region:
                    break
                region_queries += 1
                for result in router.search(query, region_config, count=max_results_per_query):
                    _process_ats_result(
                        result,
                        source,
                        query,
                        location,
                        title_filters,
                        excluded_title_terms,
                        seen,
                        jobs,
                    )

    return jobs


def discover_ats_jobs_by_search(
    title_filters: list[str],
    regions: dict[str, dict],
    excluded_title_terms: list[str] | None = None,
    *,
    provider_order: list[str] | None = None,
    ats_discovery_cfg: dict | None = None,
    disabled: set[str] | None = None,
) -> list[dict]:
    """Find individual ATS job URLs from broad title+region search queries."""
    if not title_filters or not regions:
        return []

    cfg = dict(_search_cfg().get("ats_discovery", {}) or {})
    cfg.update(ats_discovery_cfg or {})
    if not cfg.get("enabled", True):
        return []

    api_cfg = load_api_config()
    if all_providers_exhausted(api_cfg):
        logger.info("[search-discovery] skipped: all providers exhausted")
        return []

    max_results_per_query = int(cfg.get("results_per_query", 10))
    max_queries_per_region = int(cfg.get("max_queries_per_region", 0) or 0)
    max_total_queries = int(cfg.get("max_total_queries", 0) or 0)
    sources = cfg.get("sources") or list(_ATS_DISCOVERY_SITES)
    router = ProviderSearchRouter(provider_order or _provider_order(), disabled=disabled)
    jobs: list[dict] = []
    seen: set[str] = set()
    total_queries = 0

    for region_name, region_config in regions.items():
        region_queries = 0
        location = region_config.get("location") or region_name
        for title in title_filters:
            for source in sources:
                if source not in _ATS_DISCOVERY_SITES:
                    continue
                if max_queries_per_region > 0 and region_queries >= max_queries_per_region:
                    logger.info("[search-discovery] query cap reached for region=%s", region_name)
                    break
                if max_total_queries > 0 and total_queries >= max_total_queries:
                    logger.info("[search-discovery] total query cap reached")
                    logger.info("[search-discovery] complete: %s jobs found", len(jobs))
                    return jobs
                site_query, _, _ = _ATS_DISCOVERY_SITES[source]
                for query in _ats_search_queries(site_query, title, location):
                    if max_queries_per_region > 0 and region_queries >= max_queries_per_region:
                        logger.info("[search-discovery] query cap reached for region=%s", region_name)
                        break
                    if max_total_queries > 0 and total_queries >= max_total_queries:
                        logger.info("[search-discovery] total query cap reached")
                        logger.info("[search-discovery] complete: %s jobs found", len(jobs))
                        return jobs
                    region_queries += 1
                    total_queries += 1
                    for result in router.search(query, region_config, count=max_results_per_query):
                        _process_ats_result(
                            result,
                            source,
                            query,
                            location,
                            title_filters,
                            excluded_title_terms,
                            seen,
                            jobs,
                            log_skips=True,
                        )

    logger.info("[search-discovery] complete: %s jobs found", len(jobs))
    return jobs
