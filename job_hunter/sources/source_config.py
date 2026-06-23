"""Small config helpers shared by job-board sources."""

from __future__ import annotations

import logging
import time
from typing import Any

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
}


def source_page_cap(default: int = DEFAULT_PAGED_SOURCE_CAP) -> int:
    """Return the code-owned page cap for fragile paged sources."""
    return max(1, int(default))


def source_page_delay(default: float = DEFAULT_SOURCE_PAGE_DELAY_SECONDS) -> float:
    """Return the code-owned inter-page delay for fragile paged sources."""
    return max(0.0, float(default))


def sleep_between_pages(delay_seconds: float, page: int, max_pages: int) -> None:
    """Sleep between capped page requests when configured."""
    if delay_seconds > 0 and page < max_pages:
        time.sleep(delay_seconds)


def jobicy_geo_slug(region_cfg: dict[str, Any]) -> str:
    """Map ISO country codes to Jobicy's documented geo slugs."""
    country = str(region_cfg.get("country") or "").upper()
    slug = _JOBICY_GEO_BY_ISO.get(country, "")
    if not slug and country:
        logger.debug("[jobicy] no geo slug for country=%s; querying all remote jobs", country)
    return slug
