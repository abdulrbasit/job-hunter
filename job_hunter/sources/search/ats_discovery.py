"""ATS discovery via search: _ATS_DISCOVERY_SITES, discover_ats_jobs_by_search, location helpers."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import requests

from job_hunter.constants import ATS_DISCOVERY_API_TIMEOUT
from job_hunter.core.utils import title_matches
from job_hunter.locations import COUNTRY_NAME_TO_CODE
from job_hunter.sources._jd_ats_parsers import (
    breezy_job_ref,
    personio_job_ref,
    teamtailor_job_ref,
    workday_job_ref,
)
from job_hunter.sources.ats_urls import ats_discovery_sites, company_name_from_url
from job_hunter.sources.search._result import SearchResult
from job_hunter.sources.search._url_utils import canonicalize_url
from job_hunter.sources.search.router import (
    SearchRouter,
    _search_config,
    all_providers_exhausted,
)

logger = logging.getLogger(__name__)

# code->display-name lookup built once from the name->code map (first/primary name wins).
_CODE_TO_COUNTRY_NAME: dict[str, str] = {}
for _name, _code in COUNTRY_NAME_TO_CODE.items():
    _CODE_TO_COUNTRY_NAME.setdefault(_code, _name.title())

_GULF_CODES: frozenset[str] = frozenset({"AE", "SA", "QA", "KW", "BH", "OM"})
_GULF_QUERY_TERMS: tuple[str, ...] = (
    "Bahrain",
    "UAE",
    "Qatar",
    "Saudi",
    "Oman",
    "Kuwait",
    "Dubai",
    "Riyadh",
    "Doha",
    "Manama",
)

# Code-owned caps — not config. Keep worst-case query fan-out per (source, title) bounded.
# Sized to comfortably fit the full Gulf term set (10 terms + city/country/remote/region
# group ≈ 13 unique location terms + 1 bare-title query) without truncating it.
_MAX_QUERIES_PER_SOURCE_PER_TITLE = 16

# Conservative, code-owned title expansion — only fires when the configured title
# literally contains the base phrase, so it never invents unrelated variants.
_TITLE_VARIANT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("product manager", ("Product Owner", "Technical Product Manager")),
    ("software engineer", ("Backend Engineer", "Python Engineer")),
)


def title_query_variants(title: str) -> list[str]:
    """Derive conservative title variants for ATS discovery queries only —
    never mutates configured job_titles or any other pipeline stage."""
    lower = title.lower()
    variants: list[str] = []
    for base, extra in _TITLE_VARIANT_RULES:
        if base in lower:
            variants.extend(v for v in extra if v.lower() != lower)
    return variants


def _location_query_terms(region_config: dict, location: str) -> list[str]:
    """title+city, title+country, title+remote-country, title+region-group (Europe/
    EMEA/MENA), and Gulf city/country terms for Gulf-configured regions."""
    # Deferred import: job_hunter.sources.policy imports job_hunter.sources.search
    # (for canonicalize_url), so a module-level import here would be circular.
    from job_hunter.sources.policy import _EUROPE_COUNTRY_CODES, _MIDDLE_EAST_COUNTRY_CODES

    terms: list[str] = []
    from job_hunter.locations import location_from_region

    canonical = location_from_region(region_config) if region_config else None
    city = canonical.city.name if canonical and canonical.city is not None else str(location or "").strip()
    if city:
        terms.append(city)

    country_code = canonical.country if canonical else ""
    country_name = _CODE_TO_COUNTRY_NAME.get(country_code, "")
    if country_name and country_name.lower() != city.lower():
        terms.append(country_name)
    if country_name:
        terms.append(f"Remote {country_name}")

    if country_code in _EUROPE_COUNTRY_CODES:
        terms.append("Europe")
        terms.append("EMEA")
    if country_code in _MIDDLE_EAST_COUNTRY_CODES:
        terms.append("MENA")
        if "EMEA" not in terms:
            terms.append("EMEA")
    if country_code in _GULF_CODES:
        terms.extend(_GULF_QUERY_TERMS)

    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped


_ATS_DISCOVERY_SITES = ats_discovery_sites()


def _site_queries(site_query: str) -> list[str]:
    """Split grouped site queries into simple engine-friendly query fragments."""
    return [part.strip(" ()") for part in site_query.split(" OR ") if part.strip(" ()")]


def _ats_search_queries(
    site_query: str,
    title: str,
    location: str,
    region_config: dict | None = None,
) -> list[str]:
    """Build search queries for one ATS site × one title: title+city, title+country,
    title+remote-country, title+region-group (Europe/EMEA/MENA/Gulf), and a
    conservative set of title variants (e.g. Product Manager -> Product Owner).

    Capped at _MAX_QUERIES_PER_SOURCE_PER_TITLE per site — a code-owned ceiling,
    not config, so richer query variants can't runaway the query budget.
    """
    location_terms = _location_query_terms(region_config or {}, location)
    titles = [title, *title_query_variants(title)]
    queries: list[str] = []
    for site in _site_queries(site_query):
        for t in titles:
            title_queries = [f'{site} "{t}" "{term}"' for term in location_terms]
            title_queries.append(f'{site} "{t}"')
            queries.extend(title_queries[:_MAX_QUERIES_PER_SOURCE_PER_TITLE])
    return queries


def _passes_ats_discovery_shape(url: str, source: str) -> bool:
    _, host_pattern, path_pattern = _ATS_DISCOVERY_SITES[source]
    parsed = urlparse(url)
    return (
        re.search(host_pattern, parsed.netloc, re.IGNORECASE) is not None
        and re.search(path_pattern, parsed.path, re.IGNORECASE) is not None
    )


# Each evidence function returns the posting's location strings from the ATS
# API, or None when the location is unknown/unfetchable (treated as a match —
# unknown must never drop a job). Matching itself is centralized in JobPolicy
# via _ats_location_matches_policy, never done here.


def _lever_locations(url: str) -> list[str] | None:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 2:
        return None
    slug, job_id = parts[0], parts[1]
    resp = requests.get(f"https://api.lever.co/v0/postings/{slug}/{job_id}", timeout=ATS_DISCOVERY_API_TIMEOUT)
    if not resp.ok:
        return None
    categories = resp.json().get("categories", {})
    primary = categories.get("location", "")
    all_locs = [str(loc) for loc in (categories.get("allLocations") or ([primary] if primary else [])) if str(loc)]
    return all_locs or None


def _greenhouse_locations(url: str) -> list[str] | None:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 3:
        return None  # shape gate upstream guarantees valid JD URLs; defensive only
    slug, job_id = parts[0], parts[2]
    resp = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}", timeout=ATS_DISCOVERY_API_TIMEOUT
    )
    if not resp.ok:
        return None
    location = resp.json().get("location", {}).get("name", "")
    return [location] if location else None


def _ashby_locations(url: str) -> list[str] | None:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 2:
        return None
    slug, job_id = parts[0], parts[1]
    resp = requests.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}/job-posting/{job_id}",
        timeout=ATS_DISCOVERY_API_TIMEOUT,
    )
    if not resp.ok:
        return None
    location = resp.json().get("jobPosting", {}).get("locationName", "")
    return [location] if location else None


def _smartrecruiters_locations(url: str) -> list[str] | None:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 2:
        return None
    slug, posting_id = parts[0], parts[1]
    resp = requests.get(
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}",
        timeout=ATS_DISCOVERY_API_TIMEOUT,
    )
    if not resp.ok:
        return None
    loc = resp.json().get("location", {})
    evidence = [v for v in (loc.get("city", ""), loc.get("country", "")) if v]
    return evidence or None


def _workable_locations(url: str) -> list[str] | None:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 3:
        return None
    slug, shortcode = parts[0], parts[2]
    resp = requests.get(
        f"https://apply.workable.com/api/v3/accounts/{slug}/jobs/{shortcode}", timeout=ATS_DISCOVERY_API_TIMEOUT
    )
    if not resp.ok:
        return None
    location = resp.json().get("location", {}).get("location", "")
    return [location] if location else None


def _recruitee_locations(url: str) -> list[str] | None:
    parsed = urlparse(url)
    subdomain = parsed.netloc.split(".recruitee.com", 1)[0]
    slug = parsed.path.strip("/").split("/")[-1]
    if not subdomain or not slug:
        return None
    resp = requests.get(f"https://{subdomain}.recruitee.com/api/offers/{slug}", timeout=ATS_DISCOVERY_API_TIMEOUT)
    if not resp.ok:
        return None
    offer = resp.json().get("offer", {})
    evidence = [v for v in (offer.get("city", ""), offer.get("location", "")) if v]
    return evidence or None


def _personio_locations(url: str) -> list[str] | None:
    ref = personio_job_ref(url)
    if not ref:
        return None
    slug, job_id = ref
    resp = requests.get(f"https://{slug}.jobs.personio.de/xml", timeout=ATS_DISCOVERY_API_TIMEOUT)
    if not resp.ok:
        return None
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(resp.text)  # noqa: S314
    except ET.ParseError:
        return None
    for position in root.findall("position"):
        if (position.findtext("id") or "").strip() != job_id:
            continue
        offices = [(position.findtext("office") or "").strip()]
        offices.extend(o.strip() for o in (e.text or "" for e in position.findall("additionalOffices/office")) if o)
        offices = [o for o in offices if o]
        return offices or None
    return None


def _breezy_locations(url: str) -> list[str] | None:
    ref = breezy_job_ref(url)
    if not ref:
        return None
    slug, friendly_id = ref
    resp = requests.get(f"https://{slug}.breezy.hr/json", timeout=ATS_DISCOVERY_API_TIMEOUT)
    if not resp.ok:
        return None
    data = resp.json()
    if not isinstance(data, list):
        return None
    for item in data:
        if not isinstance(item, dict) or item.get("friendly_id") != friendly_id:
            continue
        loc = item.get("location") or {}
        city = loc.get("city", "") if isinstance(loc, dict) else ""
        country = (loc.get("country") or {}).get("name", "") if isinstance(loc, dict) else ""
        evidence = [v for v in (city, country) if v]
        return evidence or None
    return None


def _teamtailor_locations(url: str) -> list[str] | None:
    slug = teamtailor_job_ref(url)
    if not slug:
        return None
    resp = requests.get(f"https://{slug}.teamtailor.com/jobs.json", timeout=ATS_DISCOVERY_API_TIMEOUT)
    if not resp.ok:
        return None
    data = resp.json()
    for item in (data.get("items") or []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or item.get("url") != url:
            continue
        locations = ((item.get("_jobposting") or {}).get("jobLocation")) or []
        if not locations:
            return None
        address = (locations[0] or {}).get("address") or {}
        evidence = [v for v in (address.get("addressLocality", ""), address.get("addressCountry", "")) if v]
        return evidence or None
    return None


def _workday_locations(url: str) -> list[str] | None:
    ref = workday_job_ref(url)
    if not ref:
        return None
    tenant, wd_host, site, external_path = ref
    api_url = f"https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{external_path}"
    resp = requests.get(api_url, timeout=ATS_DISCOVERY_API_TIMEOUT)
    if not resp.ok:
        return None
    info = resp.json().get("jobPostingInfo", {})
    location = info.get("location", "") or info.get("country", "")
    return [location] if location else None


_ATS_LOCATION_EVIDENCE = {
    "lever": _lever_locations,
    "greenhouse": _greenhouse_locations,
    "ashby": _ashby_locations,
    "smartrecruiters": _smartrecruiters_locations,
    "workable": _workable_locations,
    "recruitee": _recruitee_locations,
    "personio": _personio_locations,
    "breezy": _breezy_locations,
    "teamtailor": _teamtailor_locations,
    "workday": _workday_locations,
}
_ATS_LOCATION_VERIFIABLE = frozenset(_ATS_LOCATION_EVIDENCE)


def _ats_location_evidence(url: str, source: str) -> list[str] | None:
    """Fetch the posting's location strings from the ATS API; None when unknown."""
    fetcher = _ATS_LOCATION_EVIDENCE.get(source)
    if not fetcher:
        return None
    try:
        return fetcher(url)
    except Exception as e:
        logger.debug("[ats_discovery] location evidence skipped: %s", e)
        return None


def _ats_location_matches_policy(url: str, source: str, region_config: dict | None, fallback_location: str) -> bool:
    """Decide location compatibility for the no-enriched-location fallback path.

    ATS API evidence is judged by the same JobPolicy rules as enriched locations
    — country-level ("Germany"), remote-country, and broad-region ("Europe"/
    "EMEA"/"MENA"/"GCC"/"Middle East") evidence matches its region instead of
    being substring-compared against the configured city. Unknown evidence is a
    match: unknown must never drop a job.
    """
    from job_hunter.sources.policy import JobPolicy

    evidence = _ats_location_evidence(url, source)
    if not evidence:
        return True
    candidate = {"location": evidence[0], "location_restrictions": evidence}
    policy = JobPolicy({})
    effective_region_config = region_config or {"location": fallback_location}
    return not (
        policy.has_incompatible_location_metadata(candidate, effective_region_config)
        or policy.has_wrong_location(candidate, effective_region_config)
    )


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
    region_name: str,
    region_config: dict | None = None,
    *,
    log_skips: bool = False,
) -> None:
    """Enrich, filter, and append a single search result to jobs (mutates seen and jobs)."""
    # Deferred import: job_hunter.sources.policy imports job_hunter.sources.search
    # (for canonicalize_url), so a module-level import here would be circular.
    from job_hunter.sources.policy import JobPolicy

    if not _passes_ats_discovery_shape(result.url, source):
        return
    canonical = canonicalize_url(result.url)
    if canonical in seen:
        return
    seen.add(canonical)
    enriched = _enrich_ats_discovery_job(result.url)
    if enriched and enriched.get("job_description_fetch_status") == "position_closed":
        logger.info("  [skip] Position closed: %s", result.url)
        return None
    job_title = enriched.get("title", "") if enriched else result.title
    if not title_matches(job_title, title_filters, excluded_title_terms):
        return
    enriched_location = str((enriched or {}).get("location") or "")
    candidate = {
        "title": enriched.get("title", job_title) if enriched else job_title,
        "company": (enriched or {}).get("company") or company_name_from_url(result.url) or "",
        "location": enriched_location or location,
        "url": result.url,
        "posted_date_text": (enriched or {}).get("posted_date_text", ""),
        "snippet": (enriched or {}).get("snippet", result.description),
        "source": (
            f"{result.source} ATS discovery: {source} API" if enriched else f"{result.source} ATS discovery: {source}"
        ),
        "search_query": query,
        "location_restrictions": [enriched_location] if enriched_location else [],
        "region": region_name,
    }
    if enriched_location:
        # JobPolicy is the source of truth for location compatibility: it accepts
        # country-level ("Germany"), remote-country ("Remote Germany"), and broad
        # region ("Europe"/"EMEA"/"MENA"/"GCC"/"Middle East") locations that a
        # plain substring match against the configured city would wrongly drop,
        # while still rejecting wrong-country restrictions ("United States").
        policy = JobPolicy({})
        effective_region_config = region_config or {"location": location}
        if policy.has_incompatible_location_metadata(candidate, effective_region_config) or policy.has_wrong_location(
            candidate, effective_region_config
        ):
            if log_skips:
                logger.debug(
                    "[search-discovery] %s location mismatch, skipping: %s",
                    source,
                    result.url,
                )
            return
    elif source in _ATS_LOCATION_VERIFIABLE and not _ats_location_matches_policy(
        result.url, source, region_config, location
    ):
        # ATS API evidence fallback: only when enrichment yielded no location.
        if log_skips:
            logger.debug(
                "[search-discovery] %s location mismatch, skipping: %s",
                source,
                result.url,
            )
        return
    jobs.append(candidate)


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
    from job_hunter.locations import location_from_region

    canonical = location_from_region(region_config)
    location = canonical.city.name if canonical.city is not None else canonical.country or "Remote"
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
            for query in _ats_search_queries(site_query, title, location, region_config):
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
                        region_name,
                        region_config,
                    )

    return jobs


def discover_ats_jobs_by_search(
    title_filters: list[str],
    regions: dict[str, dict],
    excluded_title_terms: list[str] | None = None,
    *,
    ats_discovery_config: dict | None = None,
    disabled: set[str] | None = None,
) -> list[dict]:
    """Find individual ATS job URLs from broad title+region search queries."""
    if not title_filters or not regions:
        return []

    config = dict(_search_config().get("ats_discovery", {}) or {})
    config.update(ats_discovery_config or {})
    if not config.get("enabled", True):
        return []

    if all_providers_exhausted():
        logger.info("[search-discovery] skipped: all providers exhausted")
        return []

    max_results_per_query = int(config.get("results_per_query", 10))
    max_queries_per_region = int(config.get("max_queries_per_region", 0) or 0)
    max_total_queries = int(config.get("max_total_queries", 0) or 0)
    sources = config.get("sources") or list(_ATS_DISCOVERY_SITES)
    router = SearchRouter(disabled=disabled)
    jobs: list[dict] = []
    seen: set[str] = set()
    total_queries = 0

    for region_name, region_config in regions.items():
        region_queries = 0
        from job_hunter.locations import location_from_region

        canonical = location_from_region(region_config)
        location = canonical.city.name if canonical.city is not None else canonical.country or "Remote"
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
                for query in _ats_search_queries(site_query, title, location, region_config):
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
                            region_name,
                            region_config,
                            log_skips=True,
                        )

    logger.info("[search-discovery] complete: %s jobs found", len(jobs))
    return jobs
