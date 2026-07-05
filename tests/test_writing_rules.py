from __future__ import annotations

from job_hunter.writing.rules import (
    as_prompt_block,
    universal_ats_rules,
    universal_cover_letter_rules,
    universal_evidence_rules,
    universal_outreach_rules,
    universal_resume_rules,
    universal_score_decision_rules,
)


def test_evidence_context_returns_universal_evidence_rules() -> None:
    from job_hunter.agent_context.evidence_context import evidence_context

    result = evidence_context()

    assert result == {"writing_rules": {"evidence": list(universal_evidence_rules())}}


def test_all_universal_rule_sets_are_nonempty_tuples_of_str() -> None:
    for rules in (
        universal_resume_rules(),
        universal_cover_letter_rules(),
        universal_outreach_rules(),
        universal_evidence_rules(),
        universal_ats_rules(),
        universal_score_decision_rules(),
    ):
        assert isinstance(rules, tuple)
        assert rules
        assert all(isinstance(r, str) and r for r in rules)


def test_universal_resume_rules_include_evidence_and_ats_rules() -> None:
    resume_rules = universal_resume_rules()
    for rule in universal_evidence_rules():
        assert rule in resume_rules
    for rule in universal_ats_rules():
        assert rule in resume_rules


def test_as_prompt_block_renders_title_and_bullets() -> None:
    block = as_prompt_block("TITLE", ("a", "b"))

    assert block == "TITLE:\n- a\n- b"


def test_outreach_context_returns_universal_outreach_rules() -> None:
    from job_hunter.agent_context.outreach_context import outreach_context

    result = outreach_context()

    assert result == {"writing_rules": {"outreach": list(universal_outreach_rules())}}
