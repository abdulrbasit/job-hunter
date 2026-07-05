from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from job_hunter.models import JobPosting


def _sample_posting() -> JobPosting:
    from job_hunter.models import JobPosting

    return JobPosting(
        title="Software Engineer",
        company="Acme Corp",
        url="https://acme.com/jobs/1",
        location="Berlin",
        snippet="Work on cool stuff",
        source="Greenhouse API",
        posted_date_text="2024-01-01",
        region="de",
        search_query="Software Engineer Berlin",
        extraction_method="ats_api",
        source_url="https://acme.com",
    )


def test_round_trip() -> None:
    jp = _sample_posting()
    from job_hunter.models import JobPosting

    assert JobPosting.model_validate(jp.model_dump()) == jp


def test_extra_keys_dropped() -> None:
    jp = _sample_posting()
    from job_hunter.models import JobPosting

    d = jp.model_dump()
    d["unknown_field"] = "should be dropped"
    result = JobPosting.model_validate(d)
    assert result == jp


def test_hunt_output_snapshot_path_is_optional() -> None:
    from pathlib import Path

    from job_hunter.models import HuntOutput

    default = HuntOutput()
    assert default.snapshot_path is None

    with_path = HuntOutput(snapshot_path=Path("outputs/state/hunt_scrape_2026-01-01.json"))
    assert with_path.snapshot_path == Path("outputs/state/hunt_scrape_2026-01-01.json")


def test_job_posting_field_names_are_the_phase_6_renamed_names() -> None:
    """Regression guard for the Phase 6 field renames — locks in the new names and
    confirms the old, pre-rename names are gone (no dead compat aliases kept)."""
    from job_hunter.models import JobPosting

    fields = JobPosting.model_fields
    renamed = {
        "full_job_description",
        "posting_date_status",
        "job_description_fetch_status",
        "llm_posting_status_check",
        "search_query",
        "posted_date_text",
    }
    assert renamed <= fields.keys()

    old_names = {"full_jd", "date_status", "fetch_status", "llm_open_check", "query", "posted"}
    assert not (old_names & fields.keys())


def test_job_posting_defaults() -> None:
    from job_hunter.models import JobPosting

    jp = JobPosting(title="PM", company="Acme", url="https://acme.com/jobs/1")

    assert jp.location == ""
    assert jp.posted_date_text == ""
    assert jp.search_query == ""
    assert jp.full_job_description == ""
    assert jp.posting_date_status == ""
    assert jp.job_description_fetch_status == ""
    assert jp.llm_posting_status_check == ""
    assert jp.location_restrictions == []
    assert jp.seniority == []


def test_job_posting_fetch_status_rejects_invalid_literal() -> None:
    import pytest
    from pydantic import ValidationError

    from job_hunter.models import JobPosting

    with pytest.raises(ValidationError):
        JobPosting(title="PM", company="Acme", url="https://acme.com/jobs/1", job_description_fetch_status="bogus")


def test_dead_scoring_and_context_models_were_removed() -> None:
    """Phase 6: ScoreResult, JobScore, TailorResult, CoverResult, AgentBatchContext, ScoreContext,
    and BriefingContext had zero production usage (only defined, never constructed) and were removed
    rather than kept as speculative/aspirational models."""
    import job_hunter.models as models

    for name in (
        "ScoreResult",
        "JobScore",
        "TailorResult",
        "CoverResult",
        "AgentBatchContext",
        "ScoreContext",
        "BriefingContext",
        "SnapshotPayload",
    ):
        assert not hasattr(models, name), f"{name} should have been removed as dead code"


def test_search_params_defaults() -> None:
    from job_hunter.models import SearchParams

    params = SearchParams(region_key="primary", country="DE", location="Berlin", search_lang="en", job_titles=["PM"])

    assert params.max_results == 50
    assert params.excluded_title_terms == []


def test_scrape_stats_defaults() -> None:
    from job_hunter.models import ScrapeStats

    stats = ScrapeStats()

    assert stats.total_fetched == 0
    assert stats.by_source == {}
    assert stats.duration_seconds == 0.0


def test_hunt_input_requires_valid_mode() -> None:
    import pytest
    from pydantic import ValidationError

    from job_hunter.models import HuntInput

    with pytest.raises(ValidationError):
        HuntInput(region_key="primary", mode="not-a-real-mode")

    valid = HuntInput(region_key="primary", mode="agent")
    assert valid.depth == "standard"
    assert valid.scrape_only is False


def test_hunt_input_rejects_from_db_candidates_in_agent_mode() -> None:
    import pytest
    from pydantic import ValidationError

    from job_hunter.models import HuntInput

    with pytest.raises(ValidationError, match="/job-hunter batch"):
        HuntInput(region_key="primary", mode="agent", from_db_candidates=True)


def test_hunt_input_allows_from_db_candidates_in_llm_api_mode() -> None:
    from job_hunter.models import HuntInput

    inp = HuntInput(region_key="primary", mode="llm-api", from_db_candidates=True)
    assert inp.from_db_candidates is True


def test_hunt_input_rejects_from_db_candidates_with_scrape_only() -> None:
    import pytest
    from pydantic import ValidationError

    from job_hunter.models import HuntInput

    with pytest.raises(ValidationError, match="mutually exclusive"):
        HuntInput(region_key="primary", mode="llm-api", from_db_candidates=True, scrape_only=True)


def test_hunt_input_rejects_from_db_candidates_with_from_snapshot() -> None:
    from pathlib import Path

    import pytest
    from pydantic import ValidationError

    from job_hunter.models import HuntInput

    with pytest.raises(ValidationError, match="mutually exclusive"):
        HuntInput(
            region_key="primary",
            mode="llm-api",
            from_db_candidates=True,
            from_snapshot=Path("snap.json"),
        )


def test_models_module_has_no_dependency_on_config_cli_ux_or_sources() -> None:
    """Domain models are the lowest layer (docs/architecture.md) — importing config/cli/ux/sources
    into models.py would make a data contract depend on the code that produces or renders it."""
    import ast
    from pathlib import Path

    banned_prefixes = ("job_hunter.config", "job_hunter.cli", "job_hunter.ux", "job_hunter.sources")
    source = Path(__file__).resolve().parents[1].joinpath("job_hunter", "models.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    offenders = [name for name in imported if name.startswith(banned_prefixes)]
    assert offenders == [], f"models.py must not import: {offenders}"
