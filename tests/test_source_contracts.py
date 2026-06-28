from inspect import signature
from unittest.mock import patch

from job_hunter.models import SearchParams
from job_hunter.sources._base import JobSourceAdapter
from job_hunter.sources.boards import BOARD_REGISTRY
from job_hunter.sources.source_config import job_board_enabled, job_board_source_config, job_board_timeout


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


def test_job_board_source_config_reads_named_board_config() -> None:
    config = {"http": {"job_boards": {"example": {"enabled": False, "timeout_seconds": 9}}}}

    with patch("job_hunter.sources.source_config.get_api_config", return_value=config):
        assert job_board_source_config("example") == {"enabled": False, "timeout_seconds": 9}
        assert job_board_enabled("example") is False


def test_job_board_timeout_uses_source_timeout_before_default() -> None:
    config = {"http": {"job_boards": {"example": {"timeout_seconds": 9}, "fallback": {}}}}

    with (
        patch("job_hunter.sources.source_config.get_api_config", return_value=config),
        patch("job_hunter.sources.source_config.get_timeout", return_value=4),
    ):
        assert job_board_timeout("example") == 9
        assert job_board_timeout("fallback") == 4
