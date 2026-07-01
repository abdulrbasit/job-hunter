"""Tests for sources/source_config.py's page-derivation helper."""

from job_hunter.constants import DEFAULT_STANDARD_MAX_RESULTS, MAX_SAFE_PAGES_PER_SOURCE
from job_hunter.sources.source_config import (
    DEFAULT_PAGED_SOURCE_CAP,
    DEFAULT_SINGLE_PAGE_SOURCE_CAP,
    pages_for_max_results,
)


def test_standard_max_results_keeps_base_cap_unchanged() -> None:
    """Standard-depth requests (max_results == DEFAULT_STANDARD_MAX_RESULTS) must
    behave identically to the old flat per-source page cap — zero regression."""
    assert pages_for_max_results(DEFAULT_STANDARD_MAX_RESULTS, 20, base_cap=DEFAULT_SINGLE_PAGE_SOURCE_CAP) == 1
    assert pages_for_max_results(DEFAULT_STANDARD_MAX_RESULTS, 30, base_cap=DEFAULT_PAGED_SOURCE_CAP) == 3
    assert pages_for_max_results(DEFAULT_STANDARD_MAX_RESULTS, 99, base_cap=DEFAULT_PAGED_SOURCE_CAP) == 3


def test_below_standard_max_results_also_keeps_base_cap() -> None:
    assert pages_for_max_results(10, 20, base_cap=DEFAULT_SINGLE_PAGE_SOURCE_CAP) == 1


def test_backfill_max_results_increases_pages_beyond_base_cap() -> None:
    """The adaptive/deep-attempt signal (max_results > standard) must fetch more pages."""
    standard = pages_for_max_results(DEFAULT_STANDARD_MAX_RESULTS, 50, base_cap=DEFAULT_SINGLE_PAGE_SOURCE_CAP)
    deep = pages_for_max_results(150, 50, base_cap=DEFAULT_SINGLE_PAGE_SOURCE_CAP)
    assert deep > standard
    assert standard == 1
    assert deep == 3


def test_page_count_never_exceeds_code_owned_ceiling() -> None:
    """No config field can push page count past MAX_SAFE_PAGES_PER_SOURCE."""
    huge = pages_for_max_results(100_000, 1, base_cap=1)
    assert huge == MAX_SAFE_PAGES_PER_SOURCE


def test_page_count_never_goes_below_one() -> None:
    assert pages_for_max_results(0, 0, base_cap=0) == 1


def test_deep_max_results_never_shrinks_pages_below_base_cap() -> None:
    """A large page_size relative to backfill max_results must not reduce pages below base_cap."""
    assert pages_for_max_results(150, 99, base_cap=DEFAULT_PAGED_SOURCE_CAP) == DEFAULT_PAGED_SOURCE_CAP
