"""Tests for the deterministic quality gate (ranking/filtering before enrichment and LLM scoring)."""

from __future__ import annotations

from job_hunter.pipeline.quality_gate import (
    apply_pre_enrichment_quality_gate,
    apply_pre_scoring_quality_gate,
    rank_jobs_by_quality,
    score_quality_signals,
)


def _job(title: str = "Software Engineer", snippet: str = "") -> dict:
    return {"title": title, "company": "Acme", "url": "https://example.com", "snippet": snippet}


def _config(
    *,
    enabled: bool = True,
    positive_terms: list[str] | None = None,
    negative_terms: list[str] | None = None,
    min_pre_score: float = -10.0,
    max_before_enrichment: int = 200,
    max_before_llm_scoring: int = 50,
    weights: dict | None = None,
) -> dict:
    gate: dict = {
        "enabled": enabled,
        "min_pre_score": min_pre_score,
        "max_before_enrichment": max_before_enrichment,
        "max_before_llm_scoring": max_before_llm_scoring,
    }
    if positive_terms is not None:
        gate["positive_terms"] = positive_terms
    if negative_terms is not None:
        gate["negative_terms"] = negative_terms
    if weights is not None:
        gate["weights"] = weights
    return {"scoring": {"pre_llm_gate": gate}}


# ---------------------------------------------------------------------------
# score_quality_signals — scoring and reason tracking
# ---------------------------------------------------------------------------


def test_positive_title_term_increases_score():
    job = _job(title="Senior Python Developer")
    result = score_quality_signals(job, _config(positive_terms=["python"]))
    assert result["_quality_score"] == 3.0


def test_negative_title_term_reduces_score_with_title_weight():
    job_title = _job(title="Senior Manager")
    job_snippet = _job(title="Engineer", snippet="seeking a manager for the team")
    config = _config(negative_terms=["manager"])
    assert score_quality_signals(job_title, config)["_quality_score"] == -5.0
    assert score_quality_signals(job_snippet, config)["_quality_score"] == -2.0


def test_snippet_positive_term_uses_snippet_weight():
    job = _job(snippet="experience with python required")
    result = score_quality_signals(job, _config(positive_terms=["python"]))
    assert result["_quality_score"] == 1.0


def test_snippet_negative_term_uses_snippet_weight():
    job = _job(snippet="must speak german fluently")
    result = score_quality_signals(job, _config(negative_terms=["german"]))
    assert result["_quality_score"] == -2.0


def test_quality_reasons_records_positive_match():
    job = _job(title="Python Developer", snippet="python experience")
    result = score_quality_signals(job, _config(positive_terms=["python"]))
    assert "title:+python" in result["_quality_reasons"]
    assert "snippet:+python" in result["_quality_reasons"]


def test_quality_reasons_records_negative_match():
    job = _job(title="Sales Manager", snippet="manage a sales team")
    result = score_quality_signals(job, _config(negative_terms=["manager"]))
    assert "title:-manager" in result["_quality_reasons"]
    assert "snippet:-manager" not in result["_quality_reasons"]  # "manager" not in snippet text


def test_term_matching_is_case_insensitive():
    job = _job(title="PYTHON DEVELOPER", snippet="Experience With PYTHON")
    result = score_quality_signals(job, _config(positive_terms=["Python"]))
    assert result["_quality_score"] == 4.0  # title 3.0 + snippet 1.0


def test_quality_score_and_reasons_fields_always_present():
    job = _job()
    result = score_quality_signals(job, _config())
    assert "_quality_score" in result
    assert "_quality_reasons" in result


def test_empty_terms_lists_score_all_jobs_zero():
    job = _job(title="Data Scientist", snippet="machine learning and python")
    result = score_quality_signals(job, _config(positive_terms=[], negative_terms=[]))
    assert result["_quality_score"] == 0.0
    assert result["_quality_reasons"] == []


# ---------------------------------------------------------------------------
# rank_jobs_by_quality
# ---------------------------------------------------------------------------


def test_rank_jobs_sorts_descending():
    jobs = [
        {**_job(title="A"), "_quality_score": 1.0, "_quality_reasons": []},
        {**_job(title="B"), "_quality_score": 5.0, "_quality_reasons": []},
        {**_job(title="C"), "_quality_score": -2.0, "_quality_reasons": []},
    ]
    ranked = rank_jobs_by_quality(jobs, _config())
    scores = [j["_quality_score"] for j in ranked]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# apply_pre_enrichment_quality_gate
# ---------------------------------------------------------------------------


def test_max_before_enrichment_caps_kept_jobs():
    jobs = [_job(title=f"Job {i}") for i in range(100)]
    kept, rejected = apply_pre_enrichment_quality_gate(jobs, _config(max_before_enrichment=10))
    assert len(kept) == 10
    assert len(rejected) == 90


def test_max_before_enrichment_does_not_apply_min_pre_score():
    # A job with a strongly negative score must still be kept if under the cap.
    job = _job(title="Sales Manager")
    config = _config(negative_terms=["manager"], min_pre_score=0.0, max_before_enrichment=5)
    kept, rejected = apply_pre_enrichment_quality_gate([job], config)
    assert len(kept) == 1
    assert len(rejected) == 0


def test_disabled_gate_returns_all_jobs_unchanged_pre_enrichment():
    jobs = [_job(title=f"Job {i}") for i in range(50)]
    kept, rejected = apply_pre_enrichment_quality_gate(jobs, _config(enabled=False))
    assert kept is jobs
    assert rejected == []


# ---------------------------------------------------------------------------
# apply_pre_scoring_quality_gate
# ---------------------------------------------------------------------------


def test_max_before_llm_scoring_caps_kept_jobs():
    jobs = [_job(title=f"Job {i}") for i in range(100)]
    kept, rejected = apply_pre_scoring_quality_gate(jobs, _config(max_before_llm_scoring=20))
    assert len(kept) == 20
    assert len(rejected) == 80


def test_min_pre_score_rejects_jobs_below_threshold():
    job_bad = _job(title="Sales Manager")  # score = -5.0 with negative term
    job_ok = _job(title="Software Engineer")
    config = _config(negative_terms=["manager"], min_pre_score=-3.0, max_before_llm_scoring=50)
    kept, rejected = apply_pre_scoring_quality_gate([job_bad, job_ok], config)
    titles_kept = [j["title"] for j in kept]
    titles_rejected = [j["title"] for j in rejected]
    assert "Software Engineer" in titles_kept
    assert "Sales Manager" in titles_rejected


def test_min_pre_score_keeps_jobs_at_exact_threshold():
    # score == threshold → kept (boundary: >=)
    job = _job(title="Sales Manager")  # title_negative = -5.0
    config = _config(negative_terms=["manager"], min_pre_score=-5.0, max_before_llm_scoring=50)
    kept, rejected = apply_pre_scoring_quality_gate([job], config)
    assert len(kept) == 1
    assert len(rejected) == 0


def test_apply_pre_scoring_quality_gate_respects_both_min_score_and_cap():
    # 5 jobs: 3 score 0.0 (pass threshold), cap=2 → kept=2, rejected=3
    jobs = [_job(title=f"Engineer {i}") for i in range(3)]
    bad_jobs = [_job(title="Sales Manager") for _ in range(2)]  # score -5.0
    config = _config(negative_terms=["manager"], min_pre_score=-3.0, max_before_llm_scoring=2)
    kept, rejected = apply_pre_scoring_quality_gate(jobs + bad_jobs, config)
    assert len(kept) == 2
    assert len(rejected) == 3


def test_disabled_gate_returns_all_jobs_unchanged_pre_scoring():
    jobs = [_job(title=f"Job {i}") for i in range(50)]
    kept, rejected = apply_pre_scoring_quality_gate(jobs, _config(enabled=False))
    assert kept is jobs
    assert rejected == []


# ---------------------------------------------------------------------------
# Responsibility split: quality gate ranks/caps; objective screen hard-rejects
# ---------------------------------------------------------------------------


def test_excluded_title_is_hard_rejected_by_objective_screen():
    """Hard exclusion lives in screen_jobs_by_rules (JobPolicy layer), not here."""
    from job_hunter.pipeline.stages.screening import screen_jobs_by_rules

    config = {"exclusions": {"title_terms": ["staff"]}, "regions": {}}
    kept, rejected = screen_jobs_by_rules([_job(title="Staff Product Manager")], config)

    assert kept == []
    assert len(rejected) == 1
    assert rejected[0]["_rejection_reason"] == "excluded_title"


def test_excluded_title_gets_negative_quality_reason_but_gate_alone_does_not_reject():
    """One excluded term scores -5 against the -10 default threshold: the gate
    records the signal but hard rejection is the objective screen's job."""
    config = {**_config(), "exclusions": {"title_terms": ["staff"]}}
    job = _job(title="Staff Product Manager")

    scored = score_quality_signals(job, config)
    assert "title:excluded:staff" in scored["_quality_reasons"]
    assert scored["_quality_score"] == -5.0

    kept, rejected = apply_pre_scoring_quality_gate([job], config)
    assert len(kept) == 1
    assert rejected == []
