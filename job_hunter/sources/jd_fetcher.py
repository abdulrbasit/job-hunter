"""
Fetch and parse a job description from a raw URL or pasted text.

Staged pipeline for URL fetching:
  1. ATS-specific JSON API (Greenhouse, Ashby, Lever, SmartRecruiters, Workable) — returns
     structured data directly, no HTML scraping needed.
  2. HTTP GET + strip HTML. If the page is JS-rendered and yields too little text, or the
     server returns 401/403/429, fall back to Playwright browser rendering.
  3. LLM parses the resulting plain text into structured fields (only when use_llm=True).

Playwright is optional — install it only when needed:
  python -m pip install playwright && playwright install chromium
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from job_hunter.core.config import get_timeout  # noqa: F401 — exposed for test patching
from job_hunter.core.llm_utils import extract_json_object, get_llm_role_settings
from job_hunter.core.utils import strip_html
from job_hunter.llm.client import get_client as get_llm_client
from job_hunter.sources.ats_urls import company_name_from_url

logger = logging.getLogger(__name__)

BROWSER_FETCH_STATUS_CODES = {401, 403, 429}

GREENHOUSE_API_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

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

_EXTRACT_SYSTEM = "You are a job posting parser. Return ONLY valid JSON with no markdown fences and no explanation."

_EXTRACT_PROMPT = """\
Extract the job details from this job posting page text.

URL: {url}

PAGE TEXT (first 8000 chars):
{text}

Return JSON:
{{
  "title": "exact job title from the posting",
  "company": "company name",
  "description": "the full job description text including responsibilities and requirements — at least 400 words if available"
}}

If a field cannot be found, use null."""


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _guess_title(text: str, min_chars: int, max_chars: int) -> str:
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" -|")
        if min_chars <= len(line) <= max_chars and re.search(
            r"\b(engineer|developer|manager|owner|designer|analyst|architect|lead|director|consultant)\b",
            line,
            re.IGNORECASE,
        ):
            return line
    return "Unknown Role"


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


def _fetch_playwright(url: str, timeout_ms: int = 20_000) -> str | None:
    """Render a JS-gated page with Playwright and return plain text.

    Returns None if playwright is not installed or rendering fails.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("[jd_fetcher] playwright not installed; JS rendering unavailable")
        return None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                    )
                )
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                html = page.content()
                return strip_html(html)
            finally:
                browser.close()
    except Exception as e:
        logger.warning("[jd_fetcher] Playwright failed for %s: %s", url, e)
    return None


# ---------------------------------------------------------------------------
# Greenhouse API fetcher
# ---------------------------------------------------------------------------


def _greenhouse_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if "greenhouse.io" not in parsed.netloc.lower():
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 3 and parts[1] == "jobs" and parts[2].isdigit():
        return parts[0], parts[2]
    query = parse_qs(parsed.query)
    gh_jid = (query.get("gh_jid") or query.get("token") or [""])[0]
    if len(parts) >= 2 and parts[1] == "jobs" and gh_jid.isdigit():
        return parts[0], gh_jid
    return None


def _greenhouse_api_json(api_url: str, timeout: int, **params: Any) -> dict | None:
    try:
        resp = requests.get(
            api_url,
            timeout=timeout,
            headers=GREENHOUSE_API_HEADERS,
            params=params or None,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.debug("[jd_fetcher] Greenhouse API failed for %s: %s", api_url, exc)
        return None


def _greenhouse_job_from_data(
    data: dict,
    url: str,
    company: str,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    content = strip_html(data.get("content", ""))
    title = data.get("title", "") or _guess_title(content, title_min_chars, title_max_chars)
    location = (data.get("location") or {}).get("name", "")
    if not content and not title:
        return None
    company_name = company.replace("-", " ").replace("_", " ").title()
    snippet = f"{title}\n{location}\n\n{content}".strip()[:max_description_chars]
    job_url = data.get("absolute_url") or url
    return {
        "title": title,
        "company": company_name,
        "url": job_url,
        "snippet": snippet,
        "posted": (data.get("updated_at") or "")[:10],
        "location": location,
        "source": "greenhouse_api",
    }


def _normalize_greenhouse_title(title: str, company: str = "") -> str:
    title_was_wrapped = title.lower().strip().startswith("job application for ")
    value = title.lower()
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"^job application for\s+", "", value)
    company_norm = re.sub(r"[^a-z0-9]+", " ", company.lower()).strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if company_norm and value.endswith(f" at {company_norm}"):
        value = value[: -(len(company_norm) + 4)].strip()
    elif title_was_wrapped and " at " in value:
        value = value.rsplit(" at ", 1)[0].strip()
    return value


def _greenhouse_title_match_score(expected: str, found: str, company: str = "") -> float:
    expected_norm = _normalize_greenhouse_title(expected, company)
    found_norm = _normalize_greenhouse_title(found, company)
    if not expected_norm or not found_norm:
        return 0.0
    if expected_norm == found_norm:
        return 1.0
    expected_tokens = set(expected_norm.split())
    found_tokens = set(found_norm.split())
    token_recall = len(expected_tokens & found_tokens) / max(len(expected_tokens), 1)
    sequence = SequenceMatcher(None, expected_norm, found_norm).ratio()
    return min(token_recall, sequence)


def _looks_like_greenhouse_listing_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower())
    listing_markers = (
        "current openings",
        "create a job alert",
        "search department",
        "office select",
        "powered by greenhouse",
    )
    role_markers = (
        "responsibilities",
        "requirements",
        "qualifications",
        "about the role",
        "what you'll do",
        "what you will do",
    )
    return (
        "jobs at " in normalized
        and sum(1 for m in listing_markers if m in normalized) >= 2
        and not any(m in normalized for m in role_markers)
    )


def _greenhouse_listing_match(
    listing: dict | None,
    job_id: str,
    expected_title: str,
    company: str,
) -> dict | None:
    jobs = (listing or {}).get("jobs", [])
    for item in jobs:
        if str(item.get("id")) == str(job_id):
            return item
    if not expected_title:
        return None
    scored = [
        (
            _greenhouse_title_match_score(expected_title, str(item.get("title") or ""), company),
            item,
        )
        for item in jobs
    ]
    scored.sort(key=lambda row: row[0], reverse=True)
    if not scored or scored[0][0] < 0.82:
        return None
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def _fetch_greenhouse_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
    expected_title: str = "",
) -> dict | None:
    ref = _greenhouse_job_ref(url)
    if not ref:
        return None
    company, job_id = ref
    api_base = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"

    data = _greenhouse_api_json(f"{api_base}/{job_id}", timeout)
    if data:
        job = _greenhouse_job_from_data(data, url, company, max_description_chars, title_min_chars, title_max_chars)
        if job and job.get("snippet"):
            return job

    listing = _greenhouse_api_json(api_base, timeout, content="true")
    item = _greenhouse_listing_match(listing, job_id, expected_title, company)
    if item:
        return _greenhouse_job_from_data(item, url, company, max_description_chars, title_min_chars, title_max_chars)
    return None


def is_greenhouse_listing_url(url: str) -> bool:
    """Return True for Greenhouse board/listing URLs that are not direct job postings."""
    host = urlparse(url).hostname or ""
    is_greenhouse = host == "greenhouse.io" or host.endswith(".greenhouse.io")
    return is_greenhouse and not re.search(r"/jobs/\d+", url, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Ashby API fetcher
# ---------------------------------------------------------------------------


def _ashby_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "jobs.ashbyhq.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _ashby_job_from_data(
    data: dict,
    url: str,
    company: str,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    posting = data.get("jobPosting") if "jobPosting" in data else data
    if not isinstance(posting, dict):
        return None
    content = strip_html(posting.get("descriptionHtml", ""))
    title = posting.get("title", "") or _guess_title(content, title_min_chars, title_max_chars)
    location = posting.get("locationName", "")
    if not content and not title:
        return None
    company_name = company.replace("-", " ").replace("_", " ").title()
    snippet = f"{title}\n{location}\n\n{content}".strip()[:max_description_chars]
    return {
        "title": title,
        "company": company_name,
        "url": posting.get("jobUrl") or url,
        "snippet": snippet,
        "posted": (posting.get("publishedAt") or "")[:10],
        "location": location,
        "source": "ashby_api",
    }


def _fetch_ashby_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    ref = _ashby_job_ref(url)
    if not ref:
        return None
    company, job_id = ref
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company}/job-posting/{job_id}"
    try:
        resp = requests.get(api_url, timeout=timeout, headers=GREENHOUSE_API_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[jd_fetcher] Ashby API failed for %s: %s", api_url, exc)
        return None
    return _ashby_job_from_data(data, url, company, max_description_chars, title_min_chars, title_max_chars)


# ---------------------------------------------------------------------------
# Lever API fetcher
# ---------------------------------------------------------------------------


def _lever_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "jobs.lever.co":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _fetch_lever_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    ref = _lever_job_ref(url)
    if not ref:
        return None
    company, posting_id = ref
    api_url = f"https://api.lever.co/v0/postings/{company}/{posting_id}"
    try:
        resp = requests.get(
            api_url,
            params={"mode": "json"},
            timeout=timeout,
            headers=GREENHOUSE_API_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[jd_fetcher] Lever API failed for %s: %s", api_url, exc)
        return None

    content = data.get("descriptionPlain") or strip_html(data.get("description", ""))
    title = data.get("text", "") or _guess_title(content, title_min_chars, title_max_chars)
    categories = data.get("categories", {}) or {}
    location = categories.get("location", "")
    if not content and not title:
        return None
    company_name = company.replace("-", " ").replace("_", " ").title()
    snippet = f"{title}\n{location}\n\n{content}".strip()[:max_description_chars]
    created_ms = data.get("createdAt")
    posted = ""
    if created_ms:
        try:
            from datetime import datetime

            posted = datetime.fromtimestamp(created_ms / 1000).strftime("%Y-%m-%d")
        except Exception:
            posted = ""
    return {
        "title": title,
        "company": company_name,
        "url": data.get("hostedUrl") or url,
        "snippet": snippet,
        "posted": posted,
        "location": location,
        "source": "lever_api",
    }


# ---------------------------------------------------------------------------
# SmartRecruiters API fetcher
# ---------------------------------------------------------------------------


def _smartrecruiters_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "jobs.smartrecruiters.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _fetch_smartrecruiters_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    ref = _smartrecruiters_job_ref(url)
    if not ref:
        return None
    company, posting_id = ref
    api_url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting_id}"
    try:
        resp = requests.get(api_url, timeout=timeout, headers=GREENHOUSE_API_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[jd_fetcher] SmartRecruiters API failed for %s: %s", api_url, exc)
        return None

    sections = data.get("jobAd", {}).get("sections", []) or []
    content = "\n\n".join(
        f"{s.get('title', '')}\n{strip_html(s.get('text', ''))}".strip()
        for s in sections
        if s.get("title") or s.get("text")
    )
    title = data.get("name", "") or _guess_title(content, title_min_chars, title_max_chars)
    loc = data.get("location", {}) or {}
    location = ", ".join(filter(None, [loc.get("city", ""), loc.get("country", "")]))
    if not content and not title:
        return None
    company_name = company.replace("-", " ").replace("_", " ").title()
    snippet = f"{title}\n{location}\n\n{content}".strip()[:max_description_chars]
    return {
        "title": title,
        "company": company_name,
        "url": url,
        "snippet": snippet,
        "posted": data.get("releasedDate", ""),
        "location": location,
        "source": "smartrecruiters_api",
    }


# ---------------------------------------------------------------------------
# Workable API fetcher
# ---------------------------------------------------------------------------


def _workable_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "apply.workable.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 3 and parts[1].lower() == "j":
        return parts[0], parts[2]
    return None


def _fetch_workable_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    ref = _workable_job_ref(url)
    if not ref:
        return None
    company, shortcode = ref
    api_url = f"https://apply.workable.com/api/v3/accounts/{company}/jobs/{shortcode}"
    try:
        resp = requests.get(api_url, timeout=timeout, headers=GREENHOUSE_API_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[jd_fetcher] Workable API failed for %s: %s", api_url, exc)
        return None

    content = strip_html(data.get("description") or data.get("description_html") or data.get("full_description") or "")
    title = data.get("title", "") or _guess_title(content, title_min_chars, title_max_chars)
    location_obj = data.get("location", {}) or {}
    location = location_obj.get("location", "") if isinstance(location_obj, dict) else str(location_obj)
    if not content and not title:
        return None
    company_name = company.replace("-", " ").replace("_", " ").title()
    snippet = f"{title}\n{location}\n\n{content}".strip()[:max_description_chars]
    return {
        "title": title,
        "company": company_name,
        "url": url,
        "snippet": snippet,
        "posted": data.get("published_on", ""),
        "location": location,
        "source": "workable_api",
    }


# ---------------------------------------------------------------------------
# LLM extraction (generic fallback for non-ATS URLs)
# ---------------------------------------------------------------------------


def _llm_extract(text: str, url: str) -> dict[str, str]:
    settings = get_llm_role_settings("jd_extraction")
    try:
        raw = get_llm_client("jd_extraction").complete(
            system=_EXTRACT_SYSTEM,
            user=_EXTRACT_PROMPT.format(text=text[:_LLM_INPUT_MAX_CHARS], url=url),
            model=settings.model,
            max_tokens=settings.max_tokens,
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
        from job_hunter.core.config import load_api_config

        return load_api_config().get("http", {}).get("jd_fetcher", {}) or {}
    except Exception:
        return {}


def fetch_jd(url: str, use_llm: bool = True, *, expected_title: str = "") -> dict | None:
    """Fetch a job description from a URL and return a pipeline-compatible job dict.

    Tries ATS-specific JSON APIs first (Greenhouse, Ashby, Lever, SmartRecruiters, Workable),
    then falls back to HTTP scraping + optional Playwright + optional LLM extraction.
    Returns None if no usable description can be extracted.
    """
    logger.info("[jd_fetcher] Fetching: %s", url)

    cfg_raw = _jd_config()

    timeout = int(cfg_raw.get("timeout_seconds", get_timeout("ats_scraper")))
    min_text_length = int(cfg_raw.get("min_text_length", _MIN_TEXT_LENGTH))
    max_description_chars = int(cfg_raw.get("max_description_chars", _FALLBACK_DESC_MAX_CHARS))
    title_min_chars = int(cfg_raw.get("title_min_chars", 8))
    title_max_chars = int(cfg_raw.get("title_max_chars", 100))

    _host = urlparse(url).hostname or ""
    is_greenhouse = _host == "greenhouse.io" or _host.endswith(".greenhouse.io")
    is_ashby = _host == "jobs.ashbyhq.com"
    is_lever = _host == "jobs.lever.co"
    is_smartrecruiters = _host == "jobs.smartrecruiters.com"
    is_workable = _host == "apply.workable.com"

    # Guard: reject Greenhouse listing pages before any fetch attempt
    if is_greenhouse_listing_url(url):
        logger.warning("[jd_fetcher] Greenhouse listing URL skipped (not a direct JD): %s", url)
        return None

    # ATS API-first path — structured JSON, no HTML scraping needed
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

    if is_ashby:
        result = _fetch_ashby_api(url, timeout, max_description_chars, title_min_chars, title_max_chars)
        if result:
            return result

    if is_lever:
        result = _fetch_lever_api(url, timeout, max_description_chars, title_min_chars, title_max_chars)
        if result:
            return result

    if is_smartrecruiters:
        result = _fetch_smartrecruiters_api(url, timeout, max_description_chars, title_min_chars, title_max_chars)
        if result:
            return result

    if is_workable:
        result = _fetch_workable_api(url, timeout, max_description_chars, title_min_chars, title_max_chars)
        if result:
            return result

    # Generic HTTP fallback (non-ATS or ATS API failure)
    html, status_code = _fetch_html(url, timeout=timeout)
    plain_text = strip_html(html or "")

    needs_browser = (
        status_code in BROWSER_FETCH_STATUS_CODES
        or len(plain_text) < min_text_length
        or (is_greenhouse and not plain_text)
    )
    if needs_browser:
        logger.info(
            "[jd_fetcher] Static fetch status=%s content=%s chars from %s; trying Playwright",
            status_code,
            len(plain_text),
            url,
        )
        pw_text = _fetch_playwright(url, timeout_ms=int(get_timeout("playwright") * 1000))
        if pw_text and len(pw_text) > len(plain_text):
            plain_text = pw_text

    if not plain_text:
        return None

    if _is_posting_inactive(plain_text):
        logger.info("[jd_fetcher] Posting appears closed/inactive: %s", url)
        return {"url": url, "snippet": "", "fetch_status": "position_closed"}

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
        "posted": "",
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
        "posted": "",
        "source": "raw_text",
    }
