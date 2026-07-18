from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch

from job_hunter.agent_context.score_context import profile_context
from job_hunter.config.reference_data import (
    experience_group_names,
    resolve_experience_group_ids,
    student_mode,
)
from job_hunter.config.service import apply_onboarding_prefs
from job_hunter.core.experience import detect_experience
from job_hunter.core.posting_types import (
    STUDENT_POSTING_TYPES,
    detect_posting_signals,
    student_query_terms,
)
from job_hunter.core.utils import title_is_allowed
from job_hunter.llm.prompts.scoring import scoring_guidance
from job_hunter.models import JobPosting, PostingType, SearchParams
from job_hunter.sources.boards.arbeitsagentur import ArbeitsagenturSource
from job_hunter.sources.boards.jobteaser import JobTeaserSource
from job_hunter.sources.boards.student_stubs import HandshakeSource, StellenwerkSource
from job_hunter.tracking.repository import get_jobs_page, insert_jobs


def test_seven_public_experience_groups_and_legacy_aliases() -> None:
    assert experience_group_names() == [
        "student",
        "entry",
        "mid",
        "senior",
        "expert",
        "management",
        "executive",
    ]
    assert resolve_experience_group_ids(["staff", "principal", "expert", "lead"]) == {"expert"}
    assert resolve_experience_group_ids(["associate", "director", "c_level"]) == {
        "entry",
        "management",
        "executive",
    }


def test_expert_and_management_are_parallel_categories() -> None:
    assert detect_experience("Principal Consultant", "").group_id == "expert"
    assert detect_experience("Staff Scientist", "").group_id == "expert"
    assert detect_experience("Team Lead", "").group_id == "expert"
    assert detect_experience("Engineering Manager", "").group_id == "management"
    assert detect_experience("Director of Research", "").group_id == "management"


def test_bare_principal_is_not_treated_as_advanced_ic() -> None:
    assert not detect_experience("School Principal", "Lead a secondary school.").confident
    assert not detect_experience("Financial Principal", "Own investments.").confident


def test_multilingual_posting_type_and_no_experience_detection() -> None:
    cases = {
        "Pflichtpraktikum Marketing": PostingType.INTERNSHIP,
        "Werkstudentin Data Analytics": PostingType.WORKING_STUDENT,
        "Masterarbeit im Bereich KI": PostingType.THESIS,
        "European Graduate Scheme": PostingType.GRADUATE_PROGRAM,
        "Traineeprogramm Einkauf": PostingType.TRAINEE,
    }
    for title, expected in cases.items():
        assert detect_posting_signals(title, "").posting_type == expected
    result = detect_posting_signals("Junior Analyst", "Keine Berufserfahrung erforderlich.")
    assert result.no_experience_required
    assert detect_posting_signals("Internal Communications Manager", "").posting_type is None


def test_student_title_matching_is_broader_but_exclusions_win() -> None:
    assert title_is_allowed(
        "Product Management Intern",
        ["Product Manager"],
        [],
        relaxed_student=True,
    )
    assert not title_is_allowed(
        "Product Management Intern",
        ["Product Manager"],
        ["intern"],
        relaxed_student=True,
    )
    assert not title_is_allowed("School Principal", ["Software Engineer"], [], relaxed_student=True)


def _config(*, levels: list[str], score: int = 70, posting_types: list[str] | None = None) -> dict:
    filters = {"hunt_languages": ["en"], "experience_levels": levels}
    if posting_types is not None:
        filters["posting_types"] = posting_types
    return {
        "mode": "agent",
        "profile": {},
        "job_titles": ["Product Manager"],
        "regions": {"primary": {"enabled": True, "country": "DE", "scope": "country"}},
        "filters": filters,
        "scoring": {"min_fit_score": score, "batch_size": 15},
        "llm": {"default_provider": "anthropic"},
    }


def test_student_mode_transition_sets_and_restores_only_defaults() -> None:
    entered = apply_onboarding_prefs(_config(levels=["entry"]), {"experience_levels": ["student"]})
    assert student_mode(entered)
    assert entered["filters"]["posting_types"] == list(STUDENT_POSTING_TYPES)
    assert entered["scoring"]["min_fit_score"] == 60

    left = apply_onboarding_prefs(entered, {"experience_levels": ["entry"]})
    assert "posting_types" not in left["filters"]
    assert left["scoring"]["min_fit_score"] == 70

    custom = apply_onboarding_prefs(
        _config(levels=["entry"], score=78),
        {"experience_levels": ["student"]},
    )
    assert custom["scoring"]["min_fit_score"] == 78


def test_posting_type_persists_and_filters_candidate_feed(tmp_path: Path) -> None:
    insert_jobs(
        tmp_path,
        [
            {"url": "https://example.com/jobs/1", "title": "Data Intern", "company": "A", "posting_type": "internship"},
            {"url": "https://example.com/jobs/2", "title": "Data Analyst", "company": "B"},
        ],
    )
    rows, total = get_jobs_page(
        tmp_path,
        statuses=("candidate",),
        posting_type="internship",
    )
    assert total == 1
    assert rows[0]["posting_type"] == "internship"

    with sqlite3.connect(tmp_path / "outputs" / "state" / "jobs.db") as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    assert "posting_type" in columns


def test_job_posting_contract_accepts_posting_type() -> None:
    posting = JobPosting(title="Intern", company="A", url="https://a/jobs/1", posting_type="internship")
    assert posting.posting_type is PostingType.INTERNSHIP


def test_student_query_terms_are_bounded_and_cover_entry_paths() -> None:
    terms = student_query_terms(["Product Manager"], {"student", "entry"})
    assert "Product Manager internship" in terms
    assert "Product Manager graduate program" in terms
    assert "Product Manager Werkstudent" in terms
    assert len(terms) <= 20


def test_arbeitsagentur_student_mode_uses_dedicated_offer_category() -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"stellenangebote": []}
    params = SearchParams(
        region_key="primary",
        country="DE",
        location="Berlin",
        search_lang="de",
        job_titles=["Product Manager"],
        query_terms=["Product Manager Praktikum"],
        student_mode=True,
    )
    with (
        patch("job_hunter.sources.boards.arbeitsagentur.requests.get", return_value=response) as request,
        patch("job_hunter.sources.boards.arbeitsagentur.get_api_config", return_value={}),
    ):
        ArbeitsagenturSource().fetch(params)
    assert request.call_args.kwargs["params"]["angebotsart"] == 34


def test_jobteaser_parser_and_inactive_stubs_use_standard_contract() -> None:
    html = """
    <article><a href="/en/job-offers/abc-data-intern"><h3>Data Intern</h3></a>
    <p>Acme</p><span>Berlin, Germany</span><span>Internship 6 months</span></article>
    """
    response = Mock(text=html)
    response.raise_for_status.return_value = None
    params = SearchParams(
        region_key="primary",
        country="DE",
        location="Berlin",
        search_lang="en",
        job_titles=["Data Analyst"],
        student_mode=True,
    )
    with patch("job_hunter.sources.boards.jobteaser.requests.get", return_value=response):
        jobs = JobTeaserSource().fetch(params)
    assert jobs[0].posting_type is PostingType.INTERNSHIP
    assert HandshakeSource().fetch(params) == []
    assert StellenwerkSource().fetch(params) == []


def test_student_scoring_guidance_is_shared_by_agent_and_llm(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "profile").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        """filters:\n  hunt_languages: [en]\n  experience_levels: [student]\nscoring:\n  min_fit_score: 60\nprofile:\n  career_context: profile/career_context.md\n""",
        encoding="utf-8",
    )
    (tmp_path / "profile" / "career_context.md").write_text("Student", encoding="utf-8")
    payload = profile_context(tmp_path)
    guidance = scoring_guidance(_config(levels=["student"], score=60))
    assert payload["student_mode"] is True
    assert "coursework" in payload["scoring_guidance"].lower()
    assert "professional tenure" in guidance.lower()
    assert "people-management" in guidance.lower()


def test_dashboard_and_readme_expose_student_flow() -> None:
    root = Path(__file__).resolve().parents[1]
    js = (root / "job_hunter" / "ux" / "web" / "dashboard.js").read_text(encoding="utf-8")
    html = (root / "job_hunter" / "ux" / "web" / "dashboard.html").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "student-mode" in js
    assert "candidate-posting-type" in html
    assert "## For Students" in readme
