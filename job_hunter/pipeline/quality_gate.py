"""Deterministic quality gate. No LLM calls — purely keyword scoring.

Two gates in the pipeline:
  apply_pre_enrichment_quality_gate — caps volume before expensive HTTP JD fetches
  apply_pre_llm_quality_gate        — filters + caps before LLM scoring calls

Scoring folds in config.exclusions.title_terms (the same deterministic title
exclusion JobPolicy and the source adapters apply) so quality/rejection reasons
show up in _pre_llm_reasons even when the gate itself is what ranks a job out.

Both are no-ops when disabled or when positive_terms/negative_terms are empty.
"""

from __future__ import annotations

import logging
from typing import Any

from job_hunter.core.utils import has_excluded_title_term

logger = logging.getLogger(__name__)

_GATE_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    # Only reject jobs with strongly negative signal (2+ negative title hits).
    # Zero-scored jobs (empty terms lists) always pass.
    "min_pre_score": -10.0,
    # Cap before HTTP enrichment. 400 scraped → at most 200 enriched.
    "max_before_enrichment": 200,
    # Main LLM token saver. 50 is generous relative to batch_size=15.
    "max_before_llm_scoring": 50,
    "weights": {
        # Title is denser signal than snippet — weight it higher.
        "title_positive": 3.0,
        "title_negative": -5.0,
        "snippet_positive": 1.0,
        "snippet_negative": -2.0,
    },
    "positive_terms": [],
    "negative_terms": [],
}


def _resolve_gate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Merge user config over defaults. Single config-lookup point."""
    user_config = config.get("scoring", {}).get("pre_llm_gate", {}) or {}
    merged = {**_GATE_DEFAULTS, **user_config}
    # Nested weights dict needs its own merge so partial overrides work.
    merged["weights"] = {**_GATE_DEFAULTS["weights"], **(user_config.get("weights") or {})}
    return merged


def score_quality_signals(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Score a job dict deterministically against positive/negative term lists.

    Adds _pre_llm_score (float) and _pre_llm_reasons (list[str]) to the job.
    Returns a new dict — does not mutate the input.
    """
    gate_config = _resolve_gate_config(config)
    if not gate_config["enabled"]:
        return {**job, "_pre_llm_score": 0.0, "_pre_llm_reasons": []}

    title = (job.get("title") or "").lower()
    snippet = (job.get("snippet") or "").lower()
    weights = gate_config["weights"]
    score = 0.0
    reasons: list[str] = []

    for term in gate_config.get("positive_terms") or []:
        t = term.lower()
        if t in title:
            score += weights["title_positive"]
            reasons.append(f"title:+{term}")
        if t in snippet:
            score += weights["snippet_positive"]
            reasons.append(f"snippet:+{term}")

    for term in gate_config.get("negative_terms") or []:
        t = term.lower()
        if t in title:
            score += weights["title_negative"]
            reasons.append(f"title:-{term}")
        if t in snippet:
            score += weights["snippet_negative"]
            reasons.append(f"snippet:-{term}")

    # Deterministic title exclusion (config.exclusions.title_terms) — same source of
    # truth as JobPolicy, applied word-order-independently via has_excluded_title_term.
    job_title = str(job.get("title") or "")
    for term in (config.get("exclusions", {}) or {}).get("title_terms", []) or []:
        if has_excluded_title_term(job_title, [term]):
            score += weights["title_negative"]
            reasons.append(f"title:excluded:{term}")

    return {**job, "_pre_llm_score": score, "_pre_llm_reasons": reasons}


def rank_jobs_by_quality(jobs: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Sort jobs by _pre_llm_score descending. Scores jobs that haven't been scored yet."""
    gate_config = _resolve_gate_config(config)
    if not gate_config["enabled"]:
        return jobs
    scored = [j if "_pre_llm_score" in j else score_quality_signals(j, config) for j in jobs]
    return sorted(scored, key=lambda j: j.get("_pre_llm_score", 0.0), reverse=True)


def apply_pre_enrichment_quality_gate(
    jobs: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Cap job volume before expensive HTTP enrichment.

    Scores and ranks all jobs, then keeps the top max_before_enrichment.
    Does NOT apply min_pre_score — before enrichment we only have title and
    sparse snippet, so a quality threshold would produce too many false negatives.

    Returns (kept, rejected).
    """
    gate_config = _resolve_gate_config(config)
    if not gate_config["enabled"]:
        return jobs, []

    scored = [score_quality_signals(j, config) for j in jobs]
    ranked = rank_jobs_by_quality(scored, config)
    cap = gate_config["max_before_enrichment"]
    return ranked[:cap], ranked[cap:]


def apply_pre_llm_quality_gate(
    jobs: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter and cap jobs before LLM scoring.

    1. Score all jobs (idempotent if already scored by score_quality_signals).
    2. Reject jobs below min_pre_score.
    3. Rank remaining by score, cap at max_before_llm_scoring.

    Returns (kept, rejected_below_threshold + rejected_by_cap).
    """
    gate_config = _resolve_gate_config(config)
    if not gate_config["enabled"]:
        return jobs, []

    scored = [score_quality_signals(j, config) for j in jobs]
    min_score = gate_config["min_pre_score"]
    above = [j for j in scored if j.get("_pre_llm_score", 0.0) >= min_score]
    below = [j for j in scored if j.get("_pre_llm_score", 0.0) < min_score]

    ranked = rank_jobs_by_quality(above, config)
    cap = gate_config["max_before_llm_scoring"]
    return ranked[:cap], ranked[cap:] + below
