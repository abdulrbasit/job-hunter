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
        posted="2024-01-01",
        region="de",
        query="Software Engineer Berlin",
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


def test_hunt_output_snapshot_path_is_optional_legacy_field() -> None:
    from pathlib import Path

    from job_hunter.models import HuntOutput

    default = HuntOutput()
    assert default.snapshot_path is None

    with_path = HuntOutput(snapshot_path=Path("outputs/state/hunt_scrape_2026-01-01.json"))
    assert with_path.snapshot_path == Path("outputs/state/hunt_scrape_2026-01-01.json")
