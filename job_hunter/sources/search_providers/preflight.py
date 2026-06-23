"""Pre-flight health checks for search and job-board providers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import requests

from job_hunter.core.api_budget import is_api_quota_exhausted, mark_api_exhausted
from job_hunter.core.config import (
    ADZUNA_API_KEY,
    ADZUNA_APP_ID,
    FIRECRAWL_API_KEY,
    JOOBLE_API_KEY,
    RAPIDAPI_KEY,
    REED_API_KEY,
    get_timeout,
    load_api_config,
)
from job_hunter.sources import (
    adzuna_source,
    arbeitsagentur_source,
    careerjet_source,
    glints_source,
    gulftalent_source,
    himalayas_source,
    job_boards,
    jobbank_source,
    jobicy_source,
    jobstreet_source,
    jooble_source,
    mycareersfuture_source,
    reed_source,
    remoteok_source,
    remotive_source,
    the_muse_source,
    weworkremotely_source,
    workingnomads_source,
)
from job_hunter.sources.search_providers.providers import (
    BraveProvider,
    ExaProvider,
    SearxngProvider,
    TavilyProvider,
)
from job_hunter.sources.source_config import jobicy_geo_slug

logger = logging.getLogger(__name__)

_PROBE_QUERY = "software engineer"
_DISABLE_STATUSES = {"blocked", "broken", "quota_exhausted", "rate_limited"}
_SKIP_STATUSES = _DISABLE_STATUSES | {"disabled", "missing_key", "not_applicable"}


@dataclass(frozen=True)
class SourceProbeResult:
    name: str
    status: str
    reason: str = ""

    @property
    def should_skip(self) -> bool:
        return self.status in _SKIP_STATUSES


def probe_search_providers() -> set[str]:
    """Test each configured search provider with a live probe query."""
    disabled: set[str] = set()

    for provider in (SearxngProvider(), BraveProvider(), TavilyProvider(), ExaProvider()):
        if not provider.enabled():
            continue
        try:
            results = provider.search(_PROBE_QUERY, {}, count=1)
            if results:
                logger.info("[preflight] %s: OK", provider.name)
            else:
                logger.warning(
                    "[preflight] %s: probe returned 0 results - disabling for this run",
                    provider.name,
                )
                disabled.add(provider.name.lower())
        except Exception as exc:
            logger.warning(
                "[preflight] %s: probe failed (%s) - disabling for this run",
                provider.name,
                exc,
            )
            disabled.add(provider.name.lower())

    if disabled:
        logger.info("[preflight] providers disabled for this run: %s", sorted(disabled))
    return disabled


def disabled_job_sources(results: dict[str, SourceProbeResult]) -> set[str]:
    """Return source names that should be skipped for this run."""
    return {name for name, result in results.items() if result.should_skip}


def probe_job_sources(
    title_filters: list[str],
    enabled_regions: dict[str, dict],
    config: dict,
) -> dict[str, SourceProbeResult]:
    """Probe enabled job-board sources once before the scraper enters loops."""
    api_cfg = load_api_config()
    boards_cfg = api_cfg.get("http", {}).get("job_boards", {}) or {}
    title = next((str(item) for item in title_filters if str(item).strip()), _PROBE_QUERY)
    results: dict[str, SourceProbeResult] = {}

    for source_name, probe in _source_probes().items():
        source_cfg = _source_cfg(boards_cfg, source_name)
        if source_cfg.get("enabled") is False:
            results[source_name] = SourceProbeResult(source_name, "disabled", "config disabled")
            continue
        try:
            results[source_name] = probe(title, enabled_regions, source_cfg, config)
        except Exception as exc:
            results[source_name] = _classify_probe_exception(source_name, exc)

    usable = sorted(name for name, result in results.items() if result.status == "ok")
    skipped = {
        status: sorted(name for name, result in results.items() if result.status == status)
        for status in sorted({result.status for result in results.values()} - {"ok"})
    }
    _log_source_health(results, usable, skipped)
    return results


def _log_source_health(results: dict[str, SourceProbeResult], usable: list[str], skipped: dict[str, list[str]]) -> None:
    logger.info("[preflight] usable job sources: %s", usable)
    if skipped:
        logger.info("[preflight] skipped job sources: %s", skipped)

    summary = {
        "usable": usable,
        "region_skipped": skipped.get("not_applicable", []),
        "missing_key": skipped.get("missing_key", []),
        "quota_exhausted": skipped.get("quota_exhausted", []),
        "blocked": skipped.get("blocked", []),
        "rate_limited": skipped.get("rate_limited", []),
        "broken": skipped.get("broken", []),
        "disabled": skipped.get("disabled", []),
    }
    logger.info("[preflight] source health summary: %s", summary)
    region_reasons = {
        name: result.reason for name, result in sorted(results.items()) if result.status == "not_applicable"
    }
    if region_reasons:
        logger.info("[preflight] region-skipped source reasons: %s", region_reasons)


def _source_cfg(boards_cfg: dict[str, Any], source_name: str) -> dict[str, Any]:
    cfg = boards_cfg.get(source_name, {}) or {}
    return cfg if isinstance(cfg, dict) else {}


def _timeout(source_cfg: dict[str, Any]) -> int:
    configured = source_cfg.get("timeout_seconds")
    try:
        return max(1, min(int(configured or get_timeout("job_boards")), 8))
    except (TypeError, ValueError):
        return 8


def _first_region(
    enabled_regions: dict[str, dict],
    *,
    countries: set[str] | None = None,
) -> tuple[str, dict] | None:
    for name, region in enabled_regions.items():
        if not isinstance(region, dict):
            continue
        if countries and str(region.get("country") or "").upper() not in countries:
            continue
        return name, region
    return None


def _missing_key(source_name: str, key_name: str) -> SourceProbeResult:
    return SourceProbeResult(source_name, "missing_key", f"{key_name} not set")


def _not_applicable(source_name: str, reason: str) -> SourceProbeResult:
    return SourceProbeResult(source_name, "not_applicable", reason)


def _ok(source_name: str, reason: str = "probe ok") -> SourceProbeResult:
    return SourceProbeResult(source_name, "ok", reason)


def _classify_probe_exception(source_name: str, exc: BaseException) -> SourceProbeResult:
    if is_api_quota_exhausted(exc):
        mark_api_exhausted(source_name, exc=exc)
        return SourceProbeResult(source_name, "quota_exhausted", str(exc)[:160])
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status == 403:
        return SourceProbeResult(source_name, "blocked", str(exc)[:160])
    if status == 429:
        return SourceProbeResult(source_name, "rate_limited", str(exc)[:160])
    return SourceProbeResult(source_name, "broken", str(exc)[:160])


def _probe_json(
    source_name: str,
    request: Callable[[], requests.Response],
    *,
    allow_list: bool = False,
) -> SourceProbeResult:
    try:
        resp = request()
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict) and not (allow_list and isinstance(payload, list)):
            return SourceProbeResult(source_name, "broken", "malformed JSON response")
        return _ok(source_name)
    except Exception as exc:
        return _classify_probe_exception(source_name, exc)


def _probe_html(source_name: str, request: Callable[[], requests.Response]) -> SourceProbeResult:
    try:
        resp = request()
        resp.raise_for_status()
        if not isinstance(getattr(resp, "text", ""), str):
            return SourceProbeResult(source_name, "broken", "malformed HTML response")
        return _ok(source_name)
    except Exception as exc:
        return _classify_probe_exception(source_name, exc)


def _probe_rss(source_name: str, request: Callable[[], requests.Response]) -> SourceProbeResult:
    try:
        resp = request()
        resp.raise_for_status()
        if not getattr(resp, "content", b""):
            return SourceProbeResult(source_name, "broken", "empty RSS response")
        return _ok(source_name)
    except Exception as exc:
        return _classify_probe_exception(source_name, exc)


def _probe_adzuna(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    if not ADZUNA_APP_ID or not ADZUNA_API_KEY:
        return _missing_key("adzuna", "ADZUNA_APP_ID or ADZUNA_API_KEY")
    region = _first_region(regions, countries=set(adzuna_source._ISO_TO_ADZUNA))
    if region is None:
        return _not_applicable("adzuna", "no supported region")
    _, region_cfg = region
    country = adzuna_source._ISO_TO_ADZUNA[str(region_cfg.get("country") or "").upper()]
    location = str(region_cfg.get("location") or "")
    params: dict[str, Any] = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_API_KEY,
        "what": title,
        "results_per_page": 1,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location
    return _probe_json(
        "adzuna",
        lambda: requests.get(
            adzuna_source._BASE_URL.format(country=country, page=1),
            params=params,
            timeout=_timeout(cfg),
        ),
    )


def _probe_reed(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    if not REED_API_KEY:
        return _missing_key("reed", "REED_API_KEY")
    region = _first_region(regions, countries=set(reed_source._REED_COUNTRIES))
    if region is None:
        return _not_applicable("reed", "no GB/IE region")
    _, region_cfg = region
    params: dict[str, Any] = {"keywords": title, "resultsToTake": 1}
    if region_cfg.get("location"):
        params["locationName"] = region_cfg["location"]
    return _probe_json(
        "reed",
        lambda: requests.get(
            reed_source._SEARCH_URL,
            params=params,
            auth=(REED_API_KEY, ""),
            timeout=_timeout(cfg),
        ),
    )


def _probe_jsearch(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    if not RAPIDAPI_KEY:
        return _missing_key("jsearch", "RAPIDAPI_KEY")
    region = _first_region(regions)
    region_cfg = region[1] if region else {}
    location = str(region_cfg.get("location") or "")
    query = f"{title} in {location}" if location else title
    params: dict[str, Any] = {"query": query, "page": "1", "num_pages": "1"}
    if region_cfg.get("country"):
        params["country"] = str(region_cfg["country"]).lower()
    return _probe_json(
        "jsearch",
        lambda: requests.get(
            job_boards.JSEARCH_URL,
            headers={
                "X-RapidAPI-Key": RAPIDAPI_KEY,
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
            },
            params=params,
            timeout=_timeout(cfg),
        ),
    )


def _probe_jooble(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    if not JOOBLE_API_KEY:
        return _missing_key("jooble", "JOOBLE_API_KEY")
    region = _first_region(regions)
    location = str((region[1] if region else {}).get("location") or "")
    return _probe_json(
        "jooble",
        lambda: requests.post(
            jooble_source._BASE_URL.format(api_key=JOOBLE_API_KEY),
            json={"keywords": title, "location": location, "page": 1},
            timeout=_timeout(cfg),
        ),
    )


def _probe_firecrawl(_title: str, _regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    if not FIRECRAWL_API_KEY:
        return _missing_key("firecrawl", "FIRECRAWL_API_KEY")
    return _probe_json(
        "firecrawl",
        lambda: requests.post(
            cfg.get("api_url", "https://api.firecrawl.dev/v2/scrape"),
            headers={
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "url": "https://example.com",
                "formats": ["markdown"],
                "onlyMainContent": True,
                "timeout": _timeout(cfg) * 1000,
                "parsers": [],
            },
            timeout=_timeout(cfg) + 2,
        ),
    )


def _probe_arbeitnow(_title: str, _regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    return _probe_json(
        "arbeitnow",
        lambda: requests.get(job_boards.ARBEITNOW_URL, params={"page": 1}, timeout=_timeout(cfg)),
    )


def _probe_jobicy(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    region = _first_region(regions)
    geo = jobicy_geo_slug(region[1] if region else {})
    params: dict[str, Any] = {"count": 1, "tag": title}
    if geo:
        params["geo"] = geo
    return _probe_json(
        "jobicy",
        lambda: requests.get(jobicy_source._API_URL, params=params, timeout=_timeout(cfg)),
    )


def _probe_glints(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    region = _first_region(regions, countries=set(glints_source._SEA_CODES))
    if region is None:
        return _not_applicable("glints", "no SEA region")
    _, region_cfg = region
    return _probe_json(
        "glints",
        lambda: requests.get(
            glints_source._API_URL,
            params={
                "query": title,
                "countryCode": str(region_cfg.get("country") or "").upper(),
                "page": 1,
                "pageSize": 1,
            },
            headers=glints_source._HEADERS,
            timeout=_timeout(cfg),
        ),
        allow_list=True,
    )


def _probe_gulftalent(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    region = _first_region(regions, countries=set(gulftalent_source._GULF_CODES))
    if region is None:
        return _not_applicable("gulftalent", "no Gulf region")
    _, region_cfg = region
    country = gulftalent_source._COUNTRY_NAMES.get(str(region_cfg.get("country") or "").upper(), "")
    return _probe_html(
        "gulftalent",
        lambda: requests.get(
            gulftalent_source._SEARCH_URL,
            params={"keyword": title, "location": country},
            headers=gulftalent_source._HEADERS,
            timeout=_timeout(cfg),
        ),
    )


def _probe_jobstreet(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    region = _first_region(regions, countries=set(jobstreet_source._SEA_CONFIG))
    if region is None:
        return _not_applicable("jobstreet", "no SEA region")
    _, region_cfg = region
    site_key, domain = jobstreet_source._SEA_CONFIG[str(region_cfg.get("country") or "").upper()]
    return _probe_json(
        "jobstreet",
        lambda: requests.get(
            jobstreet_source._api_url(domain),
            params={
                "siteKey": site_key,
                "keywords": title,
                "page": 1,
                "pageSize": 1,
                "sortMode": 1,
            },
            headers=jobstreet_source._headers(domain),
            timeout=_timeout(cfg),
        ),
    )


def _probe_jobbank(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    region = _first_region(regions, countries={"CA"})
    if region is None:
        return _not_applicable("jobbank", "no CA region")
    _, region_cfg = region
    return _probe_html(
        "jobbank",
        lambda: requests.get(
            jobbank_source._SEARCH_URL,
            params={
                "searchstring": title,
                "locationstring": region_cfg.get("location", "Canada"),
                "action": "search",
                "lang": "eng",
            },
            headers=jobbank_source._HEADERS,
            timeout=_timeout(cfg),
        ),
    )


def _probe_arbeitsagentur(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    region = _first_region(regions, countries={"DE"})
    if region is None:
        return _not_applicable("arbeitsagentur", "no DE region")
    _, region_cfg = region
    return _probe_json(
        "arbeitsagentur",
        lambda: requests.get(
            arbeitsagentur_source._SEARCH_URL,
            params={"was": title, "wo": region_cfg.get("location", ""), "page": 1, "size": 1},
            headers={"X-API-Key": "jobboerse-jobsuche"},
            timeout=_timeout(cfg),
        ),
    )


def _probe_himalayas(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    region = _first_region(regions)
    region_cfg = region[1] if region else {}
    return _probe_json(
        "himalayas",
        lambda: requests.get(
            himalayas_source._SEARCH_URL,
            params={
                "q": title,
                "country": str(region_cfg.get("country") or "").upper(),
                "sort": "recent",
                "page": 1,
            },
            timeout=_timeout(cfg),
        ),
    )


def _probe_remotive(title: str, _regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    return _probe_json(
        "remotive",
        lambda: requests.get(
            remotive_source._API_URL,
            params={"search": title, "limit": 1, "page": 1},
            timeout=_timeout(cfg),
        ),
    )


def _probe_the_muse(_title: str, _regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    return _probe_json(
        "the_muse",
        lambda: requests.get(
            the_muse_source._API_URL,
            params={"page": 0, "descending": "true"},
            timeout=_timeout(cfg),
        ),
    )


def _probe_remoteok(_title: str, _regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    return _probe_json(
        "remoteok",
        lambda: requests.get(remoteok_source._API_URL, headers=remoteok_source._HEADERS, timeout=_timeout(cfg)),
        allow_list=True,
    )


def _probe_weworkremotely(_title: str, _regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    return _probe_rss(
        "weworkremotely",
        lambda: requests.get(weworkremotely_source._RSS_URL, timeout=_timeout(cfg)),
    )


def _probe_mycareersfuture(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    region = _first_region(regions, countries={"SG"})
    if region is None:
        return _not_applicable("mycareersfuture", "no SG region")
    return _probe_json(
        "mycareersfuture",
        lambda: requests.get(
            mycareersfuture_source._API_URL,
            params={"search": title, "limit": 1, "page": 0},
            headers={"Accept": "application/json"},
            timeout=_timeout(cfg),
        ),
    )


def _probe_careerjet(title: str, regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    affid = cfg.get("affid", "")
    if not affid:
        return _missing_key("careerjet", "affid not configured")
    region = _first_region(regions)
    region_cfg = region[1] if region else {}
    country = str(region_cfg.get("country") or "").upper()
    locale = careerjet_source._ISO_TO_LOCALE.get(country, "en_GB")
    return _probe_json(
        "careerjet",
        lambda: requests.get(
            careerjet_source._API_URL,
            params={
                "affid": affid,
                "keywords": title,
                "locale_code": locale,
                "pagesize": 1,
                "page": 1,
            },
            timeout=_timeout(cfg),
        ),
    )


def _probe_workingnomads(_title: str, _regions: dict[str, dict], cfg: dict, _config: dict) -> SourceProbeResult:
    return _probe_json(
        "workingnomads",
        lambda: requests.get(workingnomads_source._API_URL, timeout=_timeout(cfg)),
        allow_list=True,
    )


def _probe_jobspy(_title: str, _regions: dict[str, dict], _cfg: dict, _config: dict) -> SourceProbeResult:
    return _ok("jobspy", "library source enabled")


def _source_probes() -> dict[str, Callable[[str, dict[str, dict], dict[str, Any], dict], SourceProbeResult]]:
    return {
        "adzuna": _probe_adzuna,
        "reed": _probe_reed,
        "jsearch": _probe_jsearch,
        "jooble": _probe_jooble,
        "firecrawl": _probe_firecrawl,
        "jobicy": _probe_jobicy,
        "arbeitnow": _probe_arbeitnow,
        "glints": _probe_glints,
        "gulftalent": _probe_gulftalent,
        "jobstreet": _probe_jobstreet,
        "jobbank": _probe_jobbank,
        "arbeitsagentur": _probe_arbeitsagentur,
        "himalayas": _probe_himalayas,
        "remotive": _probe_remotive,
        "the_muse": _probe_the_muse,
        "remoteok": _probe_remoteok,
        "weworkremotely": _probe_weworkremotely,
        "mycareersfuture": _probe_mycareersfuture,
        "jobspy": _probe_jobspy,
        "careerjet": _probe_careerjet,
        "workingnomads": _probe_workingnomads,
    }
