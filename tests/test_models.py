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
    assert type(jp).from_dict(jp.to_dict()) == jp


def test_extra_keys_dropped() -> None:
    jp = _sample_posting()
    d = jp.to_dict()
    d["unknown_field"] = "should be dropped"
    result = type(jp).from_dict(d)
    assert result == jp
