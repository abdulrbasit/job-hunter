"""ATS-specific job description fetchers (Greenhouse, Ashby, Lever, SmartRecruiters, Workable).

Split from jd_fetcher.py for navigability. All public names are re-exported from jd_fetcher.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

import requests

from job_hunter.core.utils import strip_html
from job_hunter.sources._jd_ats_parsers import (
    ashby_job_ref as _ashby_job_ref,
)
from job_hunter.sources._jd_ats_parsers import (
    breezy_job_ref as _breezy_job_ref,
)
from job_hunter.sources._jd_ats_parsers import (
    greenhouse_job_ref as _greenhouse_job_ref,
)
from job_hunter.sources._jd_ats_parsers import (
    lever_job_ref as _lever_job_ref,
)
from job_hunter.sources._jd_ats_parsers import (
    personio_job_ref as _personio_job_ref,
)
from job_hunter.sources._jd_ats_parsers import (
    recruitee_job_ref as _recruitee_job_ref,
)
from job_hunter.sources._jd_ats_parsers import (
    smartrecruiters_job_ref as _smartrecruiters_job_ref,
)
from job_hunter.sources._jd_ats_parsers import (
    teamtailor_job_ref as _teamtailor_job_ref,
)
from job_hunter.sources._jd_ats_parsers import (
    workable_job_ref as _workable_job_ref,
)
from job_hunter.sources._jd_ats_parsers import (
    workday_job_ref as _workday_job_ref,
)

logger = logging.getLogger(__name__)

GREENHOUSE_API_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


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


# ---------------------------------------------------------------------------
# Greenhouse API fetcher
# ---------------------------------------------------------------------------


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
        "posted_date_text": (data.get("updated_at") or "")[:10],
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
        "posted_date_text": (posting.get("publishedAt") or "")[:10],
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
        "posted_date_text": posted,
        "location": location,
        "source": "lever_api",
    }


# ---------------------------------------------------------------------------
# SmartRecruiters API fetcher
# ---------------------------------------------------------------------------


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
        "posted_date_text": data.get("releasedDate", ""),
        "location": location,
        "source": "smartrecruiters_api",
    }


# ---------------------------------------------------------------------------
# Workable API fetcher
# ---------------------------------------------------------------------------


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
        "posted_date_text": data.get("published_on", ""),
        "location": location,
        "source": "workable_api",
    }


# ---------------------------------------------------------------------------
# Personio API fetcher (public XML feed — no JSON detail endpoint)
# ---------------------------------------------------------------------------


def _fetch_personio_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    ref = _personio_job_ref(url)
    if not ref:
        return None
    slug, job_id = ref
    api_url = f"https://{slug}.jobs.personio.de/xml"
    try:
        resp = requests.get(api_url, timeout=timeout, headers=GREENHOUSE_API_HEADERS)
        resp.raise_for_status()
        import xml.etree.ElementTree as ET

        root = ET.fromstring(resp.text)  # noqa: S314
    except Exception as exc:
        logger.debug("[jd_fetcher] Personio API failed for %s: %s", api_url, exc)
        return None

    for position in root.findall("position"):
        if (position.findtext("id") or "").strip() != job_id:
            continue
        title = (position.findtext("name") or "").strip()
        offices = [(position.findtext("office") or "").strip()]
        offices.extend(o.strip() for o in (e.text or "" for e in position.findall("additionalOffices/office")) if o)
        location = ", ".join(dict.fromkeys(o for o in offices if o))
        content = strip_html(position.findtext("jobDescriptions") or "")
        if not title:
            title = _guess_title(content, title_min_chars, title_max_chars)
        if not content and not title:
            return None
        company_name = slug.replace("-", " ").replace("_", " ").title()
        snippet = f"{title}\n{location}\n\n{content}".strip()[:max_description_chars]
        return {
            "title": title,
            "company": company_name,
            "url": url,
            "snippet": snippet,
            "posted_date_text": (position.findtext("createdAt") or "")[:10],
            "location": location,
            "source": "personio_api",
        }
    return None


# ---------------------------------------------------------------------------
# Breezy API fetcher (listing-only JSON; no per-job description field)
# ---------------------------------------------------------------------------


def _fetch_breezy_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    ref = _breezy_job_ref(url)
    if not ref:
        return None
    slug, friendly_id = ref
    api_url = f"https://{slug}.breezy.hr/json"
    try:
        resp = requests.get(api_url, timeout=timeout, headers=GREENHOUSE_API_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[jd_fetcher] Breezy API failed for %s: %s", api_url, exc)
        return None
    if not isinstance(data, list):
        return None

    for item in data:
        if not isinstance(item, dict) or item.get("friendly_id") != friendly_id:
            continue
        title = item.get("name", "") or _guess_title("", title_min_chars, title_max_chars)
        loc = item.get("location") or {}
        location = loc.get("name", "") if isinstance(loc, dict) else str(loc)
        company_name = slug.replace("-", " ").replace("_", " ").title()
        snippet = f"{title}\n{location}".strip()[:max_description_chars]
        if not title:
            return None
        return {
            "title": title,
            "company": company_name,
            "url": item.get("url") or url,
            "snippet": snippet,
            "posted_date_text": (item.get("published_date") or "")[:10],
            "location": location,
            "source": "breezy_api",
        }
    return None


# ---------------------------------------------------------------------------
# Recruitee API fetcher
# ---------------------------------------------------------------------------


def _fetch_recruitee_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    ref = _recruitee_job_ref(url)
    if not ref:
        return None
    slug, offer_slug = ref
    api_url = f"https://{slug}.recruitee.com/api/offers/{offer_slug}"
    try:
        resp = requests.get(api_url, timeout=timeout, headers=GREENHOUSE_API_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[jd_fetcher] Recruitee API failed for %s: %s", api_url, exc)
        return None

    offer = data.get("offer", data) if isinstance(data, dict) else {}
    content = strip_html(offer.get("description", "") or offer.get("requirements", ""))
    title = offer.get("title", "") or _guess_title(content, title_min_chars, title_max_chars)
    location = ", ".join(filter(None, [offer.get("city", ""), offer.get("country", "")])) or offer.get("location", "")
    if not content and not title:
        return None
    company_name = slug.replace("-", " ").replace("_", " ").title()
    snippet = f"{title}\n{location}\n\n{content}".strip()[:max_description_chars]
    return {
        "title": title,
        "company": company_name,
        "url": offer.get("careers_url") or url,
        "snippet": snippet,
        "posted_date_text": (offer.get("published_at") or "")[:10],
        "location": location,
        "source": "recruitee_api",
    }


# ---------------------------------------------------------------------------
# Teamtailor API fetcher (JSON Feed with embedded schema.org JobPosting)
# ---------------------------------------------------------------------------


def _fetch_teamtailor_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    slug = _teamtailor_job_ref(url)
    if not slug:
        return None
    api_url = f"https://{slug}.teamtailor.com/jobs.json"
    try:
        resp = requests.get(api_url, timeout=timeout, headers=GREENHOUSE_API_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[jd_fetcher] Teamtailor API failed for %s: %s", api_url, exc)
        return None

    for item in data.get("items", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or item.get("url") != url:
            continue
        posting = item.get("_jobposting") or {}
        content = strip_html(posting.get("description") or item.get("content_html") or "")
        title = item.get("title", "") or _guess_title(content, title_min_chars, title_max_chars)
        locations = posting.get("jobLocation") or []
        location = ""
        if locations and isinstance(locations, list):
            address = (locations[0] or {}).get("address") or {}
            location = ", ".join(filter(None, [address.get("addressLocality", ""), address.get("addressCountry", "")]))
        if not content and not title:
            return None
        company_name = (posting.get("hiringOrganization") or {}).get("name") or slug.replace("-", " ").title()
        snippet = f"{title}\n{location}\n\n{content}".strip()[:max_description_chars]
        return {
            "title": title,
            "company": company_name,
            "url": url,
            "snippet": snippet,
            "posted_date_text": (posting.get("datePosted") or item.get("date_published") or "")[:10],
            "location": location,
            "source": "teamtailor_api",
        }
    return None


# ---------------------------------------------------------------------------
# Workday API fetcher
# ---------------------------------------------------------------------------


def _fetch_workday_api(
    url: str,
    timeout: int,
    max_description_chars: int,
    title_min_chars: int,
    title_max_chars: int,
) -> dict | None:
    ref = _workday_job_ref(url)
    if not ref:
        return None
    tenant, wd_host, site, external_path = ref
    api_url = f"https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{external_path}"
    try:
        resp = requests.get(api_url, timeout=timeout, headers=GREENHOUSE_API_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[jd_fetcher] Workday API failed for %s: %s", api_url, exc)
        return None

    info = data.get("jobPostingInfo", {}) or {}
    content = strip_html(info.get("jobDescription") or "")
    title = info.get("title", "") or _guess_title(content, title_min_chars, title_max_chars)
    location = info.get("location", "") or info.get("country", "")
    if not content and not title:
        return None
    company_name = tenant.replace("-", " ").replace("_", " ").title()
    snippet = f"{title}\n{location}\n\n{content}".strip()[:max_description_chars]
    return {
        "title": title,
        "company": company_name,
        "url": url,
        "snippet": snippet,
        "posted_date_text": str(info.get("startDate") or "")[:10],
        "location": location,
        "source": "workday_api",
    }
