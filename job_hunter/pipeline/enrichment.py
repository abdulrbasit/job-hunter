"""Pre-validation URL and snippet enrichment helpers."""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from job_hunter.constants import MIN_FULL_JD_SNIPPET_CHARS
from job_hunter.core.config import load_api_config
from job_hunter.core.metrics import timed_stage
from job_hunter.core.utils import url_is_alive
from job_hunter.sources.jd_fetcher import fetch_jd

logger = logging.getLogger(__name__)

# JD quality status constants
JD_STATUS_FULL = "full"
JD_STATUS_SPARSE = "sparse"  # alias for thin, kept for backward compat
JD_STATUS_THIN = "thin"
JD_STATUS_EMPTY = "empty"
JD_STATUS_PAGE_NOISE = "page_noise"
JD_STATUS_FETCH_FAILED = "fetch_failed"

_NOISE_PHRASES = (
    "privacy policy",
    "job alert",
    "current openings",
    "view all jobs",
    "search jobs",
    "cookie policy",
    "cookie settings",
    "terms of service",
)
_NOISE_PHRASE_THRESHOLD = 2  # ≥2 distinct noise phrases → page noise

JDFetcher = Callable[..., dict | None]


def classify_jd_snippet(text: str | None) -> str:
    """Classify JD text quality."""
    if not text or not text.strip():
        return JD_STATUS_EMPTY
    clean = text.strip()
    lower = clean.lower()
    noise_hits = sum(1 for phrase in _NOISE_PHRASES if phrase in lower)
    if noise_hits >= _NOISE_PHRASE_THRESHOLD:
        return JD_STATUS_PAGE_NOISE
    return JD_STATUS_FULL if len(clean) >= MIN_FULL_JD_SNIPPET_CHARS else JD_STATUS_THIN


def enrich_snippets(
    jobs: list[dict],
    api_cfg: dict | None = None,
    *,
    fetcher: JDFetcher = fetch_jd,
) -> list[dict]:
    """
    Fetch full JD content for jobs with sparse or missing snippets.

    Full JD enrichment is best-effort and preserves input order. Failed fetches
    keep the original job unchanged.
    """
    if api_cfg is None:
        api_cfg = load_api_config()

    enrich_cfg = api_cfg.get("http", {}).get("jd_enrichment", {}) or {}
    max_workers = int(enrich_cfg.get("max_workers", 5))
    skip_patterns = enrich_cfg.get("skip_url_patterns") or [r"linkedin\.com/jobs/"]

    def _should_skip_enrichment(url: str) -> bool:
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in skip_patterns)

    sparse = []
    skipped = 0
    for job in jobs:
        needs_enrichment = (
            not job.get("snippet")
            or len(job.get("snippet", "")) < MIN_FULL_JD_SNIPPET_CHARS
            or job.get("source", "").startswith("Brave")
        )
        if not needs_enrichment:
            continue
        if _should_skip_enrichment(job.get("url", "")):
            skipped += 1
            continue
        sparse.append(job)
    if not sparse:
        if skipped:
            logger.info("[pipeline] Skipped enrichment for %s throttled URL(s)", skipped)
        return jobs

    logger.info("[pipeline] Enriching %s job(s) with sparse snippets...", len(sparse))
    if skipped:
        logger.info("[pipeline] Skipped enrichment for %s throttled URL(s)", skipped)

    def _fetch_one(job: dict) -> tuple[str, dict]:
        logger.info("  enriching: %s @ %s", job["title"][:50], job["company"])
        original_source = job.get("source", "")
        original_snippet = job.get("snippet", "")
        try:
            full = fetcher(job["url"], use_llm=False)
            if full and full.get("fetch_status") == "position_closed":
                logger.info("    -> posting inactive (position closed)")
                return job["url"], {**job, "fetch_status": "position_closed", "jd_status": JD_STATUS_FETCH_FAILED}
            if full and full.get("snippet"):
                new_snippet = full["snippet"]
                logger.info("    -> %s chars", len(new_snippet))
                updated = {**job, "snippet": new_snippet, "jd_status": classify_jd_snippet(new_snippet)}
                if full.get("source") and full["source"] != original_source:
                    updated["source"] = full["source"]
                    updated["original_source"] = original_source
                if original_snippet:
                    updated["search_snippet"] = original_snippet
                # Merge any additional fields from fetched result (title, location, etc.)
                for k in ("title", "company", "location"):
                    if full.get(k):
                        updated[k] = full[k]
                return job["url"], updated
        except Exception as e:
            logger.warning("    -> enrichment failed (%s), keeping original snippet", e)
            return job["url"], {**job, "jd_status": JD_STATUS_FETCH_FAILED}
        logger.warning("    -> enrichment failed, keeping original snippet")
        return job["url"], {**job, "jd_status": JD_STATUS_FETCH_FAILED}

    enriched: dict[str, dict] = {}
    with timed_stage(logger, "jd_enrichment", jobs=len(sparse), max_workers=max_workers):
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for url, enriched_job in executor.map(_fetch_one, sparse):
                enriched[url] = enriched_job

    result = [enriched.get(job["url"], job) for job in jobs]
    closed = sum(1 for j in result if j.get("fetch_status") == "position_closed")
    if closed:
        logger.info("[pipeline] %s job(s) marked position_closed during enrichment", closed)
    return result


def drop_dead_urls_before_enrichment(
    jobs: list[dict],
    api_cfg: dict,
    *,
    url_checker: Callable[[str, int], bool] = url_is_alive,
) -> list[dict]:
    """Avoid fetching full JDs for postings that already fail URL verification."""
    url_cfg = api_cfg.get("http", {}).get("url_verification", {})
    if not url_cfg.get("enabled", True):
        return jobs

    timeout = int(url_cfg.get("timeout_seconds", 5))
    max_workers = int(url_cfg.get("max_workers") or api_cfg.get("llm", {}).get("max_workers", 5))

    def _check_job(job: dict) -> tuple[bool, dict]:
        url = job.get("url", "")
        if url and not url_checker(url, timeout):
            logger.info(
                "[pipeline] Skipping dead URL before enrichment: %s @ %s",
                job.get("title", "?")[:50],
                job.get("company", "?"),
            )
            return False, job
        return True, job

    with timed_stage(logger, "url_precheck", jobs=len(jobs), max_workers=max_workers):
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            checked = list(executor.map(_check_job, jobs))

    alive = [job for ok, job in checked if ok]
    dead = [job for ok, job in checked if not ok]
    rejected = len(checked) - len(alive)

    if rejected:
        logger.info("[pipeline] Dropped %s dead URL(s) before enrichment", rejected)
        by_source = Counter(str(job.get("source") or "unknown") for job in dead)
        logger.info("[pipeline] Dead URL sources before enrichment: %s", dict(by_source))
        if jobs and not alive:
            logger.warning(
                "[pipeline] All %s scraped job URL(s) failed verification before enrichment; sources=%s",
                len(jobs),
                dict(by_source),
            )
    return alive
