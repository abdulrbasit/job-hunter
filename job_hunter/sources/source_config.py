"""Small config helpers shared by job-board sources."""

from __future__ import annotations

import logging
import time
from typing import Any

from job_hunter.config.loader import get_api_config, get_config, get_timeout
from job_hunter.constants import DEFAULT_STANDARD_MAX_RESULTS, MAX_SAFE_PAGES_PER_SOURCE

logger = logging.getLogger(__name__)

DEFAULT_SINGLE_PAGE_SOURCE_CAP = 1
DEFAULT_PAGED_SOURCE_CAP = 3
DEFAULT_SOURCE_PAGE_DELAY_SECONDS = 0.0

_JOBICY_GEO_BY_ISO: dict[str, str] = {
    "AR": "argentina",
    "AT": "austria",
    "AU": "australia",
    "BE": "belgium",
    "BG": "bulgaria",
    "BR": "brazil",
    "CA": "canada",
    "CH": "switzerland",
    "CN": "china",
    "CR": "costa-rica",
    "CY": "cyprus",
    "CZ": "czechia",
    "DE": "germany",
    "DK": "denmark",
    "EE": "estonia",
    "ES": "spain",
    "FI": "finland",
    "FR": "france",
    "GB": "uk",
    "GR": "greece",
    "HK": "hong-kong",
    "HR": "croatia",
    "HU": "hungary",
    "IE": "ireland",
    "IL": "israel",
    "IT": "italy",
    "JP": "japan",
    "KR": "south-korea",
    "LT": "lithuania",
    "LV": "latvia",
    "MX": "mexico",
    "NL": "netherlands",
    "NO": "norway",
    "NZ": "new-zealand",
    "PH": "philippines",
    "PL": "poland",
    "PT": "portugal",
    "RO": "romania",
    "RS": "serbia",
    "SE": "sweden",
    "SG": "singapore",
    "SI": "slovenia",
    "SK": "slovakia",
    "TH": "thailand",
    "TR": "turkiye",
    "UA": "ukraine",
    "UK": "uk",
    "US": "usa",
    "VN": "vietnam",
    "AE": "united-arab-emirates",
    # Extended coverage
    "CO": "colombia",
    "EG": "egypt",
    "ID": "indonesia",
    "IN": "india",
    "KE": "kenya",
    "MY": "malaysia",
    "NG": "nigeria",
    "PK": "pakistan",
    "RU": "russia",
    "ZA": "south-africa",
}


def source_page_cap(default: int = DEFAULT_PAGED_SOURCE_CAP) -> int:
    """Return the code-owned page cap for fragile paged sources."""
    return max(1, int(default))


def pages_for_max_results(max_results: int, page_size: int, *, base_cap: int = DEFAULT_PAGED_SOURCE_CAP) -> int:
    """Derive the page count needed to cover max_results at page_size per page.

    Standard-depth requests (max_results <= DEFAULT_STANDARD_MAX_RESULTS) always
    get exactly base_cap pages — identical to today's flat per-source cap, zero
    behavior change. Only a larger max_results (the adaptive/deep-attempt signal
    from orchestrator._max_results_for_depth) scales pages up beyond base_cap,
    and never past the code-owned MAX_SAFE_PAGES_PER_SOURCE ceiling — config
    cannot raise it.
    """
    base_cap = max(1, int(base_cap))
    if page_size <= 0 or max_results <= DEFAULT_STANDARD_MAX_RESULTS:
        return base_cap
    needed = -(-int(max_results) // page_size)  # ceil division
    return max(1, min(max(needed, base_cap), MAX_SAFE_PAGES_PER_SOURCE))


def source_page_delay(default: float = DEFAULT_SOURCE_PAGE_DELAY_SECONDS) -> float:
    """Return the code-owned inter-page delay for fragile paged sources."""
    return max(0.0, float(default))


def sleep_between_pages(delay_seconds: float, page: int, max_pages: int) -> None:
    """Sleep between capped page requests when configured."""
    if delay_seconds > 0 and page < max_pages:
        time.sleep(delay_seconds)


def job_board_source_config(name: str) -> dict[str, Any]:
    return get_api_config().get("http", {}).get("job_boards", {}).get(name, {}) or {}


def job_board_enabled(name: str) -> bool:
    return bool(job_board_source_config(name).get("enabled", True))


def job_board_timeout(name: str) -> int:
    return int(job_board_source_config(name).get("timeout_seconds") or get_timeout("job_boards"))


def jobicy_geo_slug(region_config: dict[str, Any]) -> str:
    """Map ISO country codes to Jobicy's documented geo slugs."""
    country = str(region_config.get("country") or "").upper()
    slug = _JOBICY_GEO_BY_ISO.get(country, "")
    if not slug and country:
        logger.debug("[jobicy] no documented geo slug for country=%s; skipping", country)
    return slug


def load_search_config() -> dict:
    config = get_config("job_hunter")
    logger.info("[sources] loaded config/job_hunter.yml")
    return config


def enabled_regions(config: dict, region: str | None = None) -> dict[str, dict]:
    regions = config.get("regions", {}) or {}
    if region:
        selected = regions.get(region)
        if not isinstance(selected, dict) or not selected.get("enabled", True):
            return {}
        return {region: selected}
    return {name: value for name, value in regions.items() if isinstance(value, dict) and value.get("enabled", True)}


def terminal_http_status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if status in {401, 402, 403, 429, 432} else None
