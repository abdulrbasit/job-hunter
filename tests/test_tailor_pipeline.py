from unittest.mock import patch

from job_hunter.cli._dispatch import _tailor_snapshot_path
from job_hunter.pipeline.tailor import run_tailor


def test_agent_tailor_links_skips_llm_and_uses_cli_hints() -> None:
    args = {
        "mode": "tailor-links",
        "links": "https://example.com/job",
        "title": "Product Manager",
        "company": "Simulation Labs",
        "force": False,
    }
    fetched = {
        "title": "Unknown Role",
        "company": "Unknown Company",
        "url": args["links"],
        "snippet": "Own product discovery, roadmap, delivery, and analytics.",
    }

    with (
        patch("job_hunter.pipeline.tailor.load_processed", return_value=set()),
        patch("job_hunter.pipeline.tailor.fetch_jd", return_value=fetched) as fetch,
    ):
        jobs, _, _ = run_tailor(args, {}, {}, None, use_llm=False)

    fetch.assert_called_once_with(args["links"], use_llm=False)
    assert jobs[0]["title"] == "Product Manager"
    assert jobs[0]["company"] == "Simulation Labs"


def test_agent_tailor_snapshots_do_not_overwrite_same_day(tmp_path) -> None:
    first = _tailor_snapshot_path(tmp_path)
    first.parent.mkdir(parents=True)
    first.write_text("first", encoding="utf-8")

    second = _tailor_snapshot_path(tmp_path)

    assert second != first
