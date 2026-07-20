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
from job_hunter.core.metrics import timed_stage
from job_hunter.core.utils import url_is_alive
from job_hunter.llm.client import get_client as get_llm_client
from job_hunter.llm.prompts.validation import PROMPT as _PROMPT
from job_hunter.llm.prompts.validation import REPAIR_PROMPT as _REPAIR_PROMPT
from job_hunter.llm.prompts.validation import SYSTEM as _SYSTEM
from job_hunter.llm.providers import resolve_model_config
from job_hunter.llm.stage import LLMStage

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

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
    api_config: dict | None = None,
    *,
    url_checker: Callable[[str, int], bool] = url_is_alive,
    excluded_industries: list[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Returns (valid_jobs, rejected_jobs).

    Rejected jobs have a ``_rejection_reason`` key added for logging.
    Jobs where LLM validation fails are passed through (fail-open) to avoid
    false negatives from transient API errors.
    """
    if api_config is None:
        api_config = get_api_config()

    stage = LLMStage(
        "validation",
        response_format="json",
        client_factory=get_llm_client,
        settings_factory=resolve_model_config,
    )

    url_config = api_config.get("http", {}).get("url_verification", {})
    check_urls = url_config.get("enabled", True)
    url_timeout = url_config.get("timeout_seconds", 5)

    max_workers = int(api_config.get("llm", {}).get("max_workers", 5))

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

        deterministic_reason = deterministic_rejection_reason(snippet, max_years)
        if deterministic_reason:
            logger.info(f"{prefix}: deterministic reject: {deterministic_reason}")
            with results_lock:
                results.append((idx_orig, "rejected", {**job, "_rejection_reason": deterministic_reason}))
            return

        try:
            prompt = _PROMPT.format(
                max_years=max_years,
                excluded_industries=", ".join(excluded_industries or []) or "none",
                snippet=snippet,
            )
            raw = stage.complete(
                system=_SYSTEM,
                user=prompt,
                api_config=api_config,
            )
            try:
                result = stage.parse_json_object(raw, "validation response must be a JSON object")
            except (json.JSONDecodeError, ValueError):
                logger.info("%s: repairing malformed validation JSON", prefix)
                repaired = stage.complete(
                    system=_SYSTEM,
                    user=_REPAIR_PROMPT.format(raw=raw[:VALIDATION_SNIPPET_CHARS]),
                    api_config=api_config,
                )
                result = stage.parse_json_object(repaired, "validation response must be a JSON object")

            if not result.get("is_active", True):
                reason = result.get("reason", "inactive")
                logger.info(f"{prefix}: inactive: {reason}")
                with results_lock:
                    results.append((idx_orig, "rejected", {**job, "_rejection_reason": reason}))
                return

            if result.get("over_experience", False):
                reason = result.get("reason", "over_experience")
                logger.info(f"{prefix}: over experience limit: {reason}")
                with results_lock:
                    results.append((idx_orig, "rejected", {**job, "_rejection_reason": reason}))
                return

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
