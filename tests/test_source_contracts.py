from inspect import signature

from job_hunter.models import SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.boards import BOARD_REGISTRY


def test_board_registry_has_one_normalized_adapter_per_source() -> None:
    adapters = [adapter_type() for adapter_type in BOARD_REGISTRY.values()]
    names = [adapter.source_name for adapter in adapters]

    assert all(isinstance(adapter, JobSourceAdapter) for adapter in adapters)
    assert all(name and name == name.lower() for name in names)
    assert len(names) == len(set(names))


def test_board_registry_preserves_worldwide_coverage() -> None:
    names = set(BOARD_REGISTRY)

    assert {"jobspy", "careerjet", "himalayas"} <= names  # global/multi-country
    assert {"arbeitsagentur", "reed"} <= names  # Europe
    assert {"jobbank", "adzuna"} <= names  # Americas
    assert {"gulftalent"} <= names  # Gulf
    assert {"mycareersfuture", "jobstreet"} <= names  # Asia-Pacific


def test_all_adapters_accept_shared_search_contract() -> None:
    params = SearchParams(
        region_key="contract",
        country="US",
        location="Remote",
        search_lang="en",
        job_titles=["Product Manager"],
        excluded_title_terms=["intern"],
    )

    for adapter_type in BOARD_REGISTRY.values():
        adapter = adapter_type()
        signature(adapter.fetch).bind(params)
