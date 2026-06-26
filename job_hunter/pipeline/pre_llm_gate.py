"""Deterministic pre-LLM quality gate. No LLM calls — purely keyword scoring.

Two gates in the pipeline:
  apply_pre_enrichment_gate  — caps volume before expensive HTTP JD fetches
  apply_pre_llm_gate         — filters + caps before LLM scoring calls

Both are no-ops when disabled or when positive_terms/negative_terms are empty.
"""

from __future__ import annotations

import logging
from typing import Any

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


def _resolve_gate_cfg(config: dict[str, Any]) -> dict[str, Any]:
    """Merge user config over defaults. Single config-lookup point."""
    user_cfg = config.get("scoring", {}).get("pre_llm_gate", {}) or {}
    merged = {**_GATE_DEFAULTS, **user_cfg}
    # Nested weights dict needs its own merge so partial overrides work.
    merged["weights"] = {**_GATE_DEFAULTS["weights"], **(user_cfg.get("weights") or {})}
    return merged


def pre_score_job(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Score a job dict deterministically against positive/negative term lists.

    Adds _pre_llm_score (float) and _pre_llm_reasons (list[str]) to the job.
    Returns a new dict — does not mutate the input.
    """
    cfg = _resolve_gate_cfg(config)
    if not cfg["enabled"]:
        return {**job, "_pre_llm_score": 0.0, "_pre_llm_reasons": []}

    title = (job.get("title") or "").lower()
    snippet = (job.get("snippet") or "").lower()
    weights = cfg["weights"]
    score = 0.0
    reasons: list[str] = []

    for term in cfg.get("positive_terms") or []:
        t = term.lower()
        if t in title:
            score += weights["title_positive"]
            reasons.append(f"title:+{term}")
        if t in snippet:
            score += weights["snippet_positive"]
            reasons.append(f"snippet:+{term}")

    for term in cfg.get("negative_terms") or []:
        t = term.lower()
        if t in title:
            score += weights["title_negative"]
            reasons.append(f"title:-{term}")
        if t in snippet:
            score += weights["snippet_negative"]
            reasons.append(f"snippet:-{term}")

    return {**job, "_pre_llm_score": score, "_pre_llm_reasons": reasons}


def rank_jobs(jobs: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Sort jobs by _pre_llm_score descending. Scores jobs that haven't been scored yet."""
    cfg = _resolve_gate_cfg(config)
    if not cfg["enabled"]:
        return jobs
    scored = [j if "_pre_llm_score" in j else pre_score_job(j, config) for j in jobs]
    return sorted(scored, key=lambda j: j.get("_pre_llm_score", 0.0), reverse=True)


def apply_pre_enrichment_gate(
    jobs: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Cap job volume before expensive HTTP enrichment.

    Scores and ranks all jobs, then keeps the top max_before_enrichment.
    Does NOT apply min_pre_score — before enrichment we only have title and
    sparse snippet, so a quality threshold would produce too many false negatives.

    Returns (kept, rejected).
    """
    cfg = _resolve_gate_cfg(config)
    if not cfg["enabled"]:
        return jobs, []

    scored = [pre_score_job(j, config) for j in jobs]
    ranked = rank_jobs(scored, config)
    cap = cfg["max_before_enrichment"]
    return ranked[:cap], ranked[cap:]


def apply_pre_llm_gate(
    jobs: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter and cap jobs before LLM scoring.

    1. Score all jobs (idempotent if already scored by pre_score_job).
    2. Reject jobs below min_pre_score.
    3. Rank remaining by score, cap at max_before_llm_scoring.

    Returns (kept, rejected_below_threshold + rejected_by_cap).
    """
    cfg = _resolve_gate_cfg(config)
    if not cfg["enabled"]:
        return jobs, []

    scored = [pre_score_job(j, config) for j in jobs]
    min_score = cfg["min_pre_score"]
    above = [j for j in scored if j.get("_pre_llm_score", 0.0) >= min_score]
    below = [j for j in scored if j.get("_pre_llm_score", 0.0) < min_score]

    ranked = rank_jobs(above, config)
    cap = cfg["max_before_llm_scoring"]
    return ranked[:cap], ranked[cap:] + below
