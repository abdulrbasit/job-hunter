"""TDD: _filter_story_bank in tailorer.py"""

from job_hunter.pipeline.tailorer import _filter_story_bank

BANK = """\
## STORY-01 Backend Scale
Some great story about scaling.
Outcome: 10x throughput.

## STORY-02 PM Discovery
Product discovery story.
Outcome: launched feature.

## STORY-03 Data Pipeline
ETL pipeline work.
Outcome: reduced latency."""


def test_filter_returns_matching_blocks():
    result = _filter_story_bank(BANK, ["STORY-01", "STORY-03"])
    assert "STORY-01" in result
    assert "STORY-03" in result
    assert "STORY-02" not in result


def test_filter_no_match_falls_back_to_full_bank():
    result = _filter_story_bank(BANK, ["STORY-99"])
    assert result == BANK


def test_filter_empty_ids_returns_full_bank():
    result = _filter_story_bank(BANK, [])
    assert result == BANK


def test_filter_empty_bank_returns_empty():
    result = _filter_story_bank("", ["STORY-01"])
    assert result == ""
