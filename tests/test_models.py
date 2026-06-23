from __future__ import annotations

import subprocess
import sys
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
    assert JobPosting.from_dict(jp.to_dict()) == jp


def test_extra_keys_dropped() -> None:
    jp = _sample_posting()
    d = jp.to_dict()
    d["unknown_field"] = "should be dropped"
    result = type(jp).from_dict(d)
    assert result == jp


def test_models_import_cleanly_in_fresh_process() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from job_hunter.models import LLMRequest, StoryBlock"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
