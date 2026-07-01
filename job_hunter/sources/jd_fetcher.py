"""
Fetch and parse a job description from a raw URL or pasted text.

Staged pipeline for URL fetching:
  1. ATS-specific JSON API (Greenhouse, Ashby, Lever, SmartRecruiters, Workable) — returns
     structured data directly, no HTML scraping needed.
  2. HTTP GET + strip HTML.
  3. LLM parses the resulting plain text into structured fields (only when use_llm=True).

Playwright browser rendering is reserved for the company browser hunt
(career_pages/__init__.py) and is not used in the main hunt pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests

from job_hunter.config.loader import get_timeout  # noqa: F401 — exposed for test patching
from job_hunter.core.llm_utils import extract_json_object
from job_hunter.core.utils import strip_html
from job_hunter.llm.client import get_client as get_llm_client
from job_hunter.llm.prompts.jd_extraction import PROMPT as _EXTRACT_PROMPT
from job_hunter.llm.prompts.jd_extraction import SYSTEM as _EXTRACT_SYSTEM
from job_hunter.llm.stage import LLMStage
from job_hunter.sources._jd_ats import (
    _fetch_ashby_api,
    _fetch_breezy_api,
    _fetch_greenhouse_api,
    _fetch_lever_api,
    _fetch_personio_api,
    _fetch_recruitee_api,
    _fetch_smartrecruiters_api,
    _fetch_teamtailor_api,
    _fetch_workable_api,
    _fetch_workday_api,
    _guess_title,
    _looks_like_greenhouse_listing_text,
    is_greenhouse_listing_url,
)
from job_hunter.sources.ats_urls import company_name_from_url

logger = logging.getLogger(__name__)

# Minimum body-text length before we consider the static extraction sufficient.
_MIN_TEXT_LENGTH = 300

_CLOSED_SIGNALS = [
    "this position has been filled",
    "no longer accepting applications",
    "job is no longer available",
    "position has been closed",
    "this job has expired",
    "posting has been removed",
    "application deadline has passed",
    "this job posting is no longer active",
    "this role has been filled",
    "this opening is no longer available",
    "job no longer exists",
    "this position is no longer open",
]


def _is_posting_inactive(text: str) -> bool:
    lower = text.lower()
    return any(signal in lower for signal in _CLOSED_SIGNALS)


_LLM_INPUT_MAX_CHARS = 8000
_FALLBACK_DESC_MAX_CHARS = 4000


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _fetch_html(url: str, timeout: int = 12) -> tuple[str | None, int | None]:
    """GET the page; return (raw_html, status_code) or (None, status_code) on failure."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
        )
        resp.raise_for_status()
        return resp.text, resp.status_code
    except requests.exceptions.HTTPError as e:
        logger.error("[jd_fetcher] HTTP %s for %s", e.response.status_code, url)
        return None, e.response.status_code
    except Exception as e:
        logger.error("[jd_fetcher] Failed to fetch %s: %s", url, e)
    return None, None


# ---------------------------------------------------------------------------
# LLM extraction (generic fallback for non-ATS URLs)
# ---------------------------------------------------------------------------


def _llm_extract(text: str, url: str) -> dict[str, str]:
    stage = LLMStage("jd_extraction", response_format="json", client_factory=get_llm_client)
    try:
        raw = stage.complete(
            system=_EXTRACT_SYSTEM,
            user=_EXTRACT_PROMPT.format(text=text[:_LLM_INPUT_MAX_CHARS], url=url),
        )
        return json.loads(extract_json_object(raw))
    except Exception as e:
        logger.warning("[jd_fetcher] LLM extraction failed (%s); falling back to raw text", e)
        return {}


def _normalize_extracted_job(extracted: Any) -> dict[str, str]:
    if isinstance(extracted, dict):
        return extracted
    if isinstance(extracted, list):
        for item in extracted:
            if isinstance(item, dict) and any(item.get(key) for key in ("title", "company", "description")):
                return item
    logger.warning(
        "[jd_fetcher] Unexpected extraction shape %s; falling back to raw text",
        type(extracted).__name__,
    )
    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _jd_config() -> dict:
    """Load jd_fetcher config section for test patching."""
    try:
        from job_hunter.config.loader import get_api_config

        return get_api_config().get("http", {}).get("jd_fetcher", {}) or {}
    except Exception:
        return {}


def fetch_jd(url: str, use_llm: bool = True, *, expected_title: str = "") -> dict | None:
    """Fetch a job description from a URL and return a pipeline-compatible job dict.

    Tries ATS-specific JSON APIs first (Greenhouse, Ashby, Lever, SmartRecruiters, Workable),
    then falls back to HTTP scraping + optional Playwright + optional LLM extraction.
    Returns None if no usable description can be extracted.
    """
    logger.info("[jd_fetcher] Fetching: %s", url)

    config_raw = _jd_config()

    timeout = int(config_raw.get("timeout_seconds", get_timeout("ats_scraper")))
    max_description_chars = int(config_raw.get("max_description_chars", _FALLBACK_DESC_MAX_CHARS))
    title_min_chars = int(config_raw.get("title_min_chars", 8))
    title_max_chars = int(config_raw.get("title_max_chars", 100))

    _host = urlparse(url).hostname or ""
    is_greenhouse = _host == "greenhouse.io" or _host.endswith(".greenhouse.io")

    # Guard: reject Greenhouse listing pages before any fetch attempt
    if is_greenhouse_listing_url(url):
        logger.warning("[jd_fetcher] Greenhouse listing URL skipped (not a direct JD): %s", url)
        return None

    # ATS API-first path — structured JSON, no HTML scraping needed. Greenhouse
    # takes an extra expected_title kwarg (listing-page disambiguation), so it's
    # handled separately from the other same-signature ATS fetchers below.
    if is_greenhouse:
        result = _fetch_greenhouse_api(
            url,
            timeout,
            max_description_chars,
            title_min_chars,
            title_max_chars,
            expected_title=expected_title,
        )
        if result:
            return result

    ats_fetchers = (
        (_host == "jobs.ashbyhq.com", _fetch_ashby_api),
        (_host == "jobs.lever.co", _fetch_lever_api),
        (_host == "jobs.smartrecruiters.com", _fetch_smartrecruiters_api),
        (_host == "apply.workable.com", _fetch_workable_api),
        (_host.endswith((".jobs.personio.de", ".jobs.personio.com")), _fetch_personio_api),
        (_host.endswith(".breezy.hr"), _fetch_breezy_api),
        (_host.endswith(".recruitee.com"), _fetch_recruitee_api),
        (_host.endswith(".teamtailor.com"), _fetch_teamtailor_api),
        (bool(re.match(r"^[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com$", _host)), _fetch_workday_api),
    )
    for matches, fetcher in ats_fetchers:
        if matches:
            result = fetcher(url, timeout, max_description_chars, title_min_chars, title_max_chars)
            if result:
                return result

    # Generic HTTP fallback (non-ATS or ATS API failure)
    html, status_code = _fetch_html(url, timeout=timeout)
    plain_text = strip_html(html or "")

    if not plain_text:
        return None

    if _is_posting_inactive(plain_text):
        logger.info("[jd_fetcher] Posting appears closed/inactive: %s", url)
        return {"url": url, "snippet": "", "job_description_fetch_status": "position_closed"}

    # Final listing-page guard for Greenhouse URLs that slipped through API
    if is_greenhouse and _looks_like_greenhouse_listing_text(plain_text):
        logger.warning("[jd_fetcher] Greenhouse URL resolved to listing page, not a JD: %s", url)
        return None

    if use_llm:
        extracted = _normalize_extracted_job(_llm_extract(plain_text, url))
        title = extracted.get("title") or _guess_title(plain_text, title_min_chars, title_max_chars)
        company = extracted.get("company") or company_name_from_url(url) or "Unknown Company"
        description = extracted.get("description") or plain_text[:max_description_chars]
    else:
        title = _guess_title(plain_text, title_min_chars, title_max_chars)
        company = company_name_from_url(url) or "Unknown Company"
        description = plain_text[:max_description_chars]

    if not description.strip():
        logger.warning("[jd_fetcher] No description extracted from %s", url)
        return None

    return {
        "title": title,
        "company": company,
        "url": url,
        "snippet": description,
        "posted_date_text": "",
        "source": "direct_link",
    }


def jd_from_text(
    text: str,
    *,
    title: str | None = None,
    company: str | None = None,
) -> dict | None:
    """Build a pipeline-compatible job dict from raw pasted job description text."""
    if not text or not text.strip():
        return None

    if not title or not company:
        extracted = _normalize_extracted_job(_llm_extract(text, "raw_text"))
        title = title or extracted.get("title") or "Unknown Role"
        company = company or extracted.get("company") or "Unknown Company"
        description = extracted.get("description") or text[:_FALLBACK_DESC_MAX_CHARS]
    else:
        description = text[:_FALLBACK_DESC_MAX_CHARS]

    if not description.strip():
        return None

    uid = hashlib.sha1(text.encode()).hexdigest()[:12]  # noqa: S324
    return {
        "title": title,
        "company": company,
        "url": f"raw://{uid}",
        "snippet": description,
        "posted_date_text": "",
        "source": "raw_text",
    }
