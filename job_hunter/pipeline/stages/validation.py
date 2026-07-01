"""
Pre-filters scraped jobs before AI scoring/tailoring.

Two checks (in order):
  1. URL reachability — HEAD-check each posting URL; drop definitive 4xx/5xx.
  2. LLM freshness check — ask a cheap model whether the snippet signals a
     closed/filled posting or an explicitly excessive experience requirement.

Running this before scorer saves the more expensive scoring and tailoring
calls on dead or obviously unsuitable postings.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from job_hunter.config.loader import get_api_config
from job_hunter.constants import VALIDATION_SNIPPET_CHARS
from job_hunter.core.llm_utils import get_llm_role_settings
from job_hunter.core.metrics import timed_stage
from job_hunter.core.utils import url_is_alive
from job_hunter.llm.client import get_client as get_llm_client
from job_hunter.pipeline.llm_stage import LLMStage

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_SYSTEM = "You are a job-posting validator. Return ONLY valid JSON with no markdown fences and no explanation."

_PROMPT = """\
Read this job posting snippet and answer three questions.

1. Is this an active, open posting?
   Mark is_active=false ONLY if the text explicitly says the role is filled,
   closed, expired, archived, or no longer accepting applications.
   When in doubt, default to true.

2. Does this posting explicitly require MORE than {max_years} years of experience?
   Mark over_experience=true ONLY if the description clearly states a minimum
   exceeding {max_years} years (e.g. "10+ years required", "minimum 8 years").
   When in doubt, default to false.

3. Is the EMPLOYER itself primarily in one of these excluded industries: {excluded_industries}?
   Do not reject because the role serves those customers, builds a related feature, or mentions
   compliance. Mark excluded_industry=true only when the employer's primary business clearly matches.
   When in doubt, default to false.

Snippet:
{snippet}

Return JSON: {{"is_active": bool, "over_experience": bool, "excluded_industry": bool,
"reason": "one-line reason if rejected, else null"}}"""

_REPAIR_PROMPT = """\
Convert this model response into valid JSON matching exactly this schema:
{{"is_active": bool, "over_experience": bool, "excluded_industry": bool, "reason": string|null}}

Rules:
- Return ONLY valid JSON.
- If a value is missing or unclear, use is_active=true, over_experience=false,
  excluded_industry=false, reason=null.

Response:
{raw}
"""

_INACTIVE_MARKERS = (
    "no longer available",
    "this job has expired",
    "position has been filled",
    "job is no longer",
    "not accepting applications",
    "this listing has closed",
    "role has been filled",
    "vacancy has been filled",
)

_EXPERIENCE_PATTERNS = (
    re.compile(
        r"\b(?:minimum|min\.?|at least|required|requires|requirement|must have|you have|you bring)"
        r"[^.\n]{0,80}?\b(\d{1,2})\+?\s*(?:years|yrs)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(\d{1,2})\+?\s*(?:years|yrs)\b[^.\n]{0,80}?"
        r"\b(?:minimum|min\.?|required|requires|requirement|must have|experience)\b",
        re.IGNORECASE,
    ),
)


def deterministic_rejection_reason(snippet: str, max_years: int) -> str | None:
    """Reject only explicit inactive postings or explicit requirements above max_years."""
    lower = snippet.lower()
    for marker in _INACTIVE_MARKERS:
        if marker in lower:
            return marker

    for pattern in _EXPERIENCE_PATTERNS:
        for match in pattern.finditer(snippet):
            years = int(match.group(1))
            if years > max_years:
                return f"requires {years}+ years experience"

    return None


def validate(
    jobs: list[dict],
    max_years: int,
    api_cfg: dict | None = None,
    *,
    url_checker: Callable[[str, int], bool] = url_is_alive,
    max_years_bypass_companies: list[str] | None = None,
    excluded_industries: list[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Returns (valid_jobs, rejected_jobs).

    Rejected jobs have a ``_rejection_reason`` key added for logging.
    Jobs where LLM validation fails are passed through (fail-open) to avoid
    false negatives from transient API errors.
    """
    if api_cfg is None:
        api_cfg = get_api_config()

    stage = LLMStage(
        "validation",
        response_format="json",
        client_factory=get_llm_client,
        settings_factory=get_llm_role_settings,
    )

    url_cfg = api_cfg.get("http", {}).get("url_verification", {})
    check_urls = url_cfg.get("enabled", True)
    url_timeout = url_cfg.get("timeout_seconds", 5)

    max_workers = int(api_cfg.get("llm", {}).get("max_workers", 5))
    bypass_companies = [company.lower() for company in (max_years_bypass_companies or [])]

    counter = 0
    counter_lock = threading.Lock()
    # Results collected in (original_index, kind, job) tuples for stable ordering
    results: list[tuple[int, str, dict]] = []
    results_lock = threading.Lock()

    def _validate_job(args: tuple[int, dict]) -> None:
        nonlocal counter
        idx_orig, job = args
        url = job.get("url", "")
        label = f"{job.get('title', '?')[:40]} @ {job.get('company', '?')}"
        with counter_lock:
            counter += 1
            display_idx = counter
        prefix = f"[validate] [{display_idx}/{len(jobs)}] {label}"
        logger.info(prefix)

        # 1 -- URL reachability
        if check_urls and url and not url_checker(url, url_timeout):
            logger.info(f"{prefix}: dead URL: {url[:80]}")
            with results_lock:
                results.append((idx_orig, "rejected", {**job, "_rejection_reason": "dead_url"}))
            return

        # 2 -- LLM freshness + experience check
        snippet = (job.get("snippet") or "")[:VALIDATION_SNIPPET_CHARS]
        if not snippet:
            with results_lock:
                results.append((idx_orig, "valid", job))
            return

        company = job.get("company", "").lower()
        bypass_max_years = any(name and name in company for name in bypass_companies)
        deterministic_reason = deterministic_rejection_reason(snippet, max_years)
        if deterministic_reason and not bypass_max_years:
            logger.info(f"{prefix}: deterministic reject: {deterministic_reason}")
            with results_lock:
                results.append((idx_orig, "rejected", {**job, "_rejection_reason": deterministic_reason}))
            return
        if deterministic_reason and bypass_max_years:
            logger.info(f"{prefix}: strategic override bypasses experience limit: {deterministic_reason}")

        try:
            prompt = _PROMPT.format(
                max_years=max_years,
                excluded_industries=", ".join(excluded_industries or []) or "none",
                snippet=snippet,
            )
            raw = stage.complete(
                system=_SYSTEM,
                user=prompt,
                api_cfg=api_cfg,
            )
            try:
                result = stage.parse_json_object(raw, "validation response must be a JSON object")
            except (json.JSONDecodeError, ValueError):
                logger.info("%s: repairing malformed validation JSON", prefix)
                repaired = stage.complete(
                    system=_SYSTEM,
                    user=_REPAIR_PROMPT.format(raw=raw[:VALIDATION_SNIPPET_CHARS]),
                    api_cfg=api_cfg,
                )
                result = stage.parse_json_object(repaired, "validation response must be a JSON object")

            if not result.get("is_active", True):
                reason = result.get("reason", "inactive")
                logger.info(f"{prefix}: inactive: {reason}")
                with results_lock:
                    results.append((idx_orig, "rejected", {**job, "_rejection_reason": reason}))
                return

            if result.get("over_experience", False) and not bypass_max_years:
                reason = result.get("reason", "over_experience")
                logger.info(f"{prefix}: over experience limit: {reason}")
                with results_lock:
                    results.append((idx_orig, "rejected", {**job, "_rejection_reason": reason}))
                return
            if result.get("over_experience", False) and bypass_max_years:
                reason = result.get("reason", "over_experience")
                logger.info(f"{prefix}: strategic override bypasses LLM experience limit: {reason}")

            if result.get("excluded_industry", False):
                reason = result.get("reason", "excluded_industry")
                logger.info(f"{prefix}: excluded employer industry: {reason}")
                with results_lock:
                    results.append((idx_orig, "rejected", {**job, "_rejection_reason": reason}))
                return

            logger.info(f"{prefix}: valid")
            with results_lock:
                results.append((idx_orig, "valid", job))

        except Exception as e:
            logger.warning(f"{prefix}: validation error ({e}) -- passing through")
            with results_lock:
                results.append((idx_orig, "valid", job))

    with timed_stage(logger, "validation", jobs=len(jobs), max_workers=max_workers):
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(_validate_job, enumerate(jobs)))

    results.sort(key=lambda t: t[0])
    valid = [job for _, kind, job in results if kind == "valid"]
    rejected = [job for _, kind, job in results if kind == "rejected"]

    logger.info(f"[validate] {len(valid)} valid, {len(rejected)} rejected of {len(jobs)}")
    return valid, rejected
