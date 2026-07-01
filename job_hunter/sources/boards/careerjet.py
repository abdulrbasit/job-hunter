"""Careerjet job board — global coverage, 90+ countries.

Free affiliate API. Register at https://www.careerjet.com/affiliate_program.html
Set the Careerjet affiliate id in provider settings when enabling this source.
Source is skipped when affid is empty.
"""

from __future__ import annotations

import logging

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.core.utils import strip_html, title_matches
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources._dates import truncate_date_text
from job_hunter.sources.source_config import source_page_cap, terminal_http_status

logger = logging.getLogger(__name__)

_API_URL = "https://search.api.careerjet.net/v4/query"
_PAGE_SIZE = 99

# ISO-3166-1 alpha-2 → Careerjet locale_code
_ISO_TO_LOCALE: dict[str, str] = {
    "AE": "ar_AE",
    "AR": "es_AR",
    "AT": "de_AT",
    "AU": "en_AU",
    "BE": "fr_BE",
    "BH": "ar_BH",
    "BR": "pt_BR",
    "CA": "en_CA",
    "CH": "de_CH",
    "CN": "zh_CN",
    "CZ": "cs_CZ",
    "DE": "de_DE",
    "DK": "da_DK",
    "ES": "es_ES",
    "FI": "fi_FI",
    "FR": "fr_FR",
    "GB": "en_GB",
    "GR": "el_GR",
    "HK": "zh_HK",
    "HU": "hu_HU",
    "ID": "id_ID",
    "IE": "en_IE",
    "IL": "he_IL",
    "IN": "en_IN",
    "IT": "it_IT",
    "JP": "ja_JP",
    "KR": "ko_KR",
    "KW": "ar_KW",
    "MX": "es_MX",
    "MY": "en_MY",
    "NL": "nl_NL",
    "NO": "no_NO",
    "NZ": "en_NZ",
    "OM": "ar_OM",
    "PH": "en_PH",
    "PK": "en_PK",
    "PL": "pl_PL",
    "PT": "pt_PT",
    "QA": "ar_QA",
    "RO": "ro_RO",
    "RU": "ru_RU",
    "SA": "ar_SA",
    "SE": "sv_SE",
    "SG": "en_SG",
    "TH": "th_TH",
    "TR": "tr_TR",
    "TW": "zh_TW",
    "UA": "uk_UA",
    "US": "en_US",
    "VE": "es_VE",
    "VN": "vi_VN",
    "ZA": "en_ZA",
    # Extended coverage
    "CL": "es_CL",
    "CO": "es_CO",
    "DZ": "ar_DZ",
    "EG": "ar_EG",
    "JO": "ar_JO",
    "LB": "ar_LB",
    "LU": "fr_LU",
    "MA": "fr_MA",
    "NG": "en_NG",
    "PE": "es_PE",
}


class CareerjetSource(JobSourceAdapter):
    tier = "api"

    @property
    def source_name(self) -> str:
        return "careerjet"

    def is_enabled(self, api_cfg: dict) -> bool:
        cfg = get_api_config().get("http", {}).get("job_boards", {}).get("careerjet", {}) or {}
        return bool(cfg.get("enabled", True)) and bool(cfg.get("affid", ""))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Fetch jobs from Careerjet's affiliate search API."""
        source_cfg = get_api_config().get("http", {}).get("job_boards", {}).get("careerjet", {}) or {}
        if not source_cfg.get("enabled", True):
            return []
        affid = source_cfg.get("affid", "")
        if not affid:
            logger.debug("[careerjet] affid not configured — skipping")
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap()
        country = params.country.upper()
        locale_code = _ISO_TO_LOCALE.get(country, "en_GB")
        location = params.location
        jobs: list[JobPosting] = []

        for title in params.job_titles:
            for page in range(1, max_pages + 1):
                req_params = {
                    "affid": affid,
                    "keywords": title,
                    "locale_code": locale_code,
                    "pagesize": _PAGE_SIZE,
                    "page": page,
                    "sort": 1,
                }
                if location:
                    req_params["location"] = location

                logger.info(
                    "[careerjet] [%s] p%d searching %r (locale=%s)",
                    params.region_key,
                    page,
                    title,
                    locale_code,
                )

                try:
                    resp = requests.get(_API_URL, params=req_params, timeout=timeout)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    if terminal_http_status(exc):
                        logger.warning("[careerjet] stopping after terminal HTTP error: %s", exc)
                        return jobs
                    logger.warning(
                        "[careerjet] request failed for %r in %s: %s",
                        title,
                        params.region_key,
                        exc,
                    )
                    break

                raw_jobs = data.get("jobs") or []
                if not isinstance(raw_jobs, list) or not raw_jobs:
                    break

                before = len(jobs)
                for item in raw_jobs:
                    if not isinstance(item, dict):
                        continue
                    job_title = str(item.get("title") or "")
                    if not title_matches(job_title, params.job_titles, []):
                        continue
                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=str(item.get("company") or ""),
                            url=str(item.get("url") or ""),
                            posted_date_text=truncate_date_text(item.get("date")),
                            location=str(item.get("locations") or location or country),
                            snippet=strip_html(str(item.get("description") or ""))[:3000],
                            source="Careerjet",
                            search_query=f"{title} @ {params.region_key}",
                            region=params.region_key,
                        )
                    )
                logger.info(
                    "[careerjet] +%d jobs for %r in %s (p%d)",
                    len(jobs) - before,
                    title,
                    params.region_key,
                    page,
                )

                total = int(data.get("total") or 0)
                if len(raw_jobs) < _PAGE_SIZE or page * _PAGE_SIZE >= total:
                    break

        logger.info("[careerjet] Complete: %d total jobs found", len(jobs))
        return jobs
