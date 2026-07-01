"""JobSpy-based job discovery via Google Jobs and Indeed.

`python-jobspy` is a required runtime dependency and JobSpy is part of the
normal scraping pipeline.

Source selection is derived automatically from each region's ISO country code
(the `country` field in config/job_hunter.yml regions). No per-region mapping config
is needed.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
from typing import Any

from job_hunter.config.loader import get_api_config
from job_hunter.core.utils import location_matches, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter

logger = logging.getLogger(__name__)

_RESULTS_PER_QUERY = 50
_SCRAPE_TIMEOUT = 45  # seconds per site call; guards against hung network requests

# Sites that returned HTTP 403 this run — never called again until process restarts.
_DISABLED_SITES: set[str] = set()
_DISABLED_SITES_LOCK = threading.Lock()


def _is_403_block(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "403" in msg or "forbidden" in msg


def _disable_site(site: str) -> None:
    with _DISABLED_SITES_LOCK:
        if site not in _DISABLED_SITES:
            _DISABLED_SITES.add(site)
            logger.warning("[jobspy] %s disabled for this run (HTTP 403 block)", site)


# ISO 3166-1 alpha-2 → jobspy Indeed country name
_ISO_TO_INDEED: dict[str, str] = {
    "AR": "argentina",
    "AU": "australia",
    "AT": "austria",
    "BH": "bahrain",
    "BD": "bangladesh",
    "BE": "belgium",
    "BG": "bulgaria",
    "BR": "brazil",
    "CA": "canada",
    "CL": "chile",
    "CN": "china",
    "CO": "colombia",
    "CR": "costa rica",
    "HR": "croatia",
    "CY": "cyprus",
    "CZ": "czech republic",
    "DK": "denmark",
    "EC": "ecuador",
    "EG": "egypt",
    "EE": "estonia",
    "FI": "finland",
    "FR": "france",
    "DE": "germany",
    "GR": "greece",
    "HK": "hong kong",
    "HU": "hungary",
    "IN": "india",
    "ID": "indonesia",
    "IE": "ireland",
    "IL": "israel",
    "IT": "italy",
    "JP": "japan",
    "KW": "kuwait",
    "LV": "latvia",
    "LT": "lithuania",
    "LU": "luxembourg",
    "MY": "malaysia",
    "MT": "malta",
    "MX": "mexico",
    "MA": "morocco",
    "NL": "netherlands",
    "NZ": "new zealand",
    "NG": "nigeria",
    "NO": "norway",
    "OM": "oman",
    "PK": "pakistan",
    "PA": "panama",
    "PE": "peru",
    "PH": "philippines",
    "PL": "poland",
    "PT": "portugal",
    "QA": "qatar",
    "RO": "romania",
    "SA": "saudi arabia",
    "SG": "singapore",
    "SK": "slovakia",
    "SI": "slovenia",
    "ZA": "south africa",
    "KR": "south korea",
    "ES": "spain",
    "SE": "sweden",
    "CH": "switzerland",
    "TW": "taiwan",
    "TH": "thailand",
    "TR": "turkey",
    "UA": "ukraine",
    "AE": "united arab emirates",
    "GB": "uk",
    "US": "usa",
    "UY": "uruguay",
    "VE": "venezuela",
    "VN": "vietnam",
}


def _str(val: Any) -> str:
    """Safe string conversion — handles None and float NaN from pandas."""
    if val is None or val != val:  # val != val is True only for NaN
        return ""
    return str(val).strip()


def _row_to_job(row: Any, region_name: str) -> dict | None:
    title = _str(row.get("title"))
    url = _str(row.get("job_url"))
    if not title or not url:
        return None

    # Prefer direct ATS URL (Greenhouse, Lever, Ashby, etc.) over the aggregator listing URL.
    # job_url_direct is populated by jobspy when LinkedIn/Indeed expose the source link.
    direct = _str(row.get("job_url_direct"))
    if direct:
        url = direct

    site = _str(row.get("site")).lower()
    return {
        "title": title,
        "company": _str(row.get("company")),
        "url": url,
        "posted_date_text": _str(row.get("date_posted")),
        "location": _str(row.get("location")),
        "snippet": _str(row.get("description"))[:3000],
        "source": f"JobSpy/{site.title()}" if site else "JobSpy",
        "search_query": f"{title} @ {region_name}",
    }


class JobSpySource(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "jobspy"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = get_api_config().get("http", {}).get("job_boards", {}).get("jobspy", {}) or {}
        return bool(cfg.get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """
        Scrape job boards via python-jobspy for each title in the region.

        Sources used (derived from region's ISO country code):
        - Google Jobs: always
        - Indeed: when the region's country has a known Indeed country name

        Skips only when disabled in config.
        """
        from jobspy import scrape_jobs

        jobspy_cfg = get_api_config().get("http", {}).get("job_boards", {}).get("jobspy", {}) or {}
        if not jobspy_cfg.get("enabled", True):
            return []

        hours_old = int(jobspy_cfg.get("hours_old", 72))
        location = params.location
        iso = params.country.upper()
        country_indeed = _ISO_TO_INDEED.get(iso, "")

        sources = ["google"]
        if country_indeed:
            sources.append("indeed")

        jobs: list[JobPosting] = []

        for title in params.job_titles:
            with _DISABLED_SITES_LOCK:
                active_sites = [s for s in sources if s not in _DISABLED_SITES]

            if not active_sites:
                logger.debug("[jobspy] all sites disabled; skipping remaining titles")
                break

            for site in active_sites:
                with _DISABLED_SITES_LOCK:
                    if site in _DISABLED_SITES:
                        continue

                logger.info("[jobspy] [%s] Searching [%s] for %r", params.region_key, site, title)
                kwargs = dict(
                    site_name=[site],
                    search_term=title,
                    google_search_term=title,
                    location=location,
                    results_wanted=_RESULTS_PER_QUERY,
                    hours_old=hours_old,
                    country_indeed=country_indeed or "usa",
                    description_format="markdown",
                    verbose=0,
                )
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(scrape_jobs, **kwargs)
                        try:
                            df = future.result(timeout=_SCRAPE_TIMEOUT)
                        except concurrent.futures.TimeoutError:
                            logger.warning(
                                "[jobspy] scrape_jobs timed out after %ds for %r via [%s]",
                                _SCRAPE_TIMEOUT,
                                title,
                                site,
                            )
                            df = None
                except Exception as exc:
                    if _is_403_block(exc):
                        _disable_site(site)
                    else:
                        logger.warning(
                            "[jobspy] scrape_jobs failed for %r in %r via [%s]: %s",
                            title,
                            location or "unknown",
                            site,
                            exc,
                        )
                    continue

                if df is None or df.empty:
                    logger.info(
                        "[jobspy] No results for %r in %r via [%s]",
                        title,
                        location,
                        site,
                    )
                    continue

                before = len(jobs)
                for _, row in df.iterrows():
                    row_title = _str(row.get("title"))
                    if not title_matches(row_title, params.job_titles, []):
                        continue
                    if location:
                        row_location = _str(row.get("location"))
                        if row_location and not location_matches(row_location, location):
                            continue
                    job_dict = _row_to_job(row, params.region_key)
                    if job_dict:
                        jobs.append(
                            JobPosting(
                                title=job_dict["title"],
                                company=job_dict["company"],
                                url=job_dict["url"],
                                posted_date_text=job_dict["posted_date_text"],
                                location=job_dict["location"],
                                snippet=job_dict["snippet"],
                                source=job_dict["source"],
                                search_query=job_dict["search_query"],
                                region=params.region_key,
                            )
                        )
                logger.info(
                    "[jobspy] +%d jobs for %r in %r via [%s]",
                    len(jobs) - before,
                    title,
                    location,
                    site,
                )

        logger.info("[jobspy] Complete: %d total jobs found", len(jobs))
        return jobs
