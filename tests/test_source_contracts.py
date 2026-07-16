import inspect
import re
from inspect import signature
from unittest.mock import patch

from job_hunter.models import SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.boards import BOARD_REGISTRY
from job_hunter.sources.source_config import job_board_enabled, job_board_source_config, job_board_timeout

# Matches a title_is_allowed(...)/title_matches(...) call that hardcodes an empty
# exclusion list instead of threading params.excluded_title_terms through.
_HARDCODED_EMPTY_EXCLUSION = re.compile(r"title_(is_allowed|matches)\([^)]*\[\]\s*\)")


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
    assert {"gulftalent", "bayt"} <= names  # Gulf
    assert {"mycareersfuture", "jobstreet"} <= names  # Asia-Pacific


def test_board_registry_has_exactly_the_expected_source_names() -> None:
    """Full membership lock — catches an accidental add/drop the coverage spot-check would miss."""
    assert set(BOARD_REGISTRY) == {
        "adzuna",
        "arbeitsagentur",
        "arbeitnow",
        "bayt",
        "careerjet",
        "gulftalent",
        "hh",
        "himalayas",
        "jobbank",
        "jobicy",
        "jobspy",
        "jobstreet",
        "mycareersfuture",
        "reed",
        "remoteok",
        "remotive",
        "the_muse",
        "weworkremotely",
        "workingnomads",
    }


def test_fetch_never_raises_when_fetch_impl_fails() -> None:
    """JobSourceAdapter.fetch() must never raise — _base.py's contract, verified for every registered adapter."""
    params = SearchParams(
        region_key="contract",
        country="US",
        location="Remote",
        search_lang="en",
        job_titles=["Product Manager"],
    )
    for adapter_type in BOARD_REGISTRY.values():
        adapter = adapter_type()
        with patch.object(adapter_type, "_fetch", side_effect=RuntimeError("boom")):
            assert adapter.fetch(params) == []


def test_all_adapters_declare_joblisting_return_contract() -> None:
    """Source adapters must return JobPosting contracts (docs/architecture.md), not raw dicts."""
    for adapter_type in BOARD_REGISTRY.values():
        annotation = signature(adapter_type._fetch).return_annotation
        assert "JobPosting" in str(annotation), f"{adapter_type.__name__}._fetch must return list[JobPosting]"


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


def test_all_board_adapters_thread_excluded_title_terms() -> None:
    """Every registered board adapter must filter titles via the shared title_is_allowed
    helper using params.excluded_title_terms — never a hardcoded empty exclusion list.

    Static/source-level check: adapters differ too much in fetch mechanics (HTML
    parsing, paginated APIs, raw dict payloads) for a single functional mock to
    exercise every one, so this asserts the actual call-site pattern instead.
    """
    checked_modules: set[str] = set()
    for source_name, adapter_type in BOARD_REGISTRY.items():
        module = inspect.getmodule(adapter_type)
        assert module is not None
        if module.__name__ in checked_modules:
            continue
        checked_modules.add(module.__name__)

        source = inspect.getsource(module)
        if "title_is_allowed(" not in source and "title_matches(" not in source:
            continue  # module has no title filtering to begin with (e.g. helper-only)

        assert "excluded_title_terms" in source, (
            f"{source_name} ({module.__name__}) filters titles but never references excluded_title_terms"
        )
        bad_call = _HARDCODED_EMPTY_EXCLUSION.search(source)
        assert bad_call is None, (
            f"{source_name} ({module.__name__}) hardcodes an empty exclusion list: {bad_call.group(0) if bad_call else ''!r}"
        )


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


def test_split_board_modules_are_registered_and_documented() -> None:
    from pathlib import Path

    from job_hunter.sources.boards.arbeitnow import ArbeitnowSource

    assert BOARD_REGISTRY["arbeitnow"] is ArbeitnowSource

    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs" / "sources.md").read_text(encoding="utf-8")
    assert "sources/boards/arbeitnow.py" in doc


# ── Registry / defaults / docs consistency ────────────────────────────────────


def test_every_registry_source_has_code_owned_http_defaults() -> None:
    """BOARD_REGISTRY and JOB_BOARD_SOURCE_NAMES must not drift: every registered
    source needs a code-owned HTTP default so it can be disabled via config."""
    from job_hunter.config.defaults import HTTP_DEFAULTS, JOB_BOARD_SOURCE_NAMES

    assert set(BOARD_REGISTRY) == set(JOB_BOARD_SOURCE_NAMES)
    for source in BOARD_REGISTRY:
        defaults = HTTP_DEFAULTS["job_boards"].get(source)
        assert isinstance(defaults, dict), f"{source} missing from HTTP_DEFAULTS['job_boards']"
        assert "enabled" in defaults, f"{source} defaults must expose an 'enabled' switch"


def test_every_source_is_disabled_by_enabled_false() -> None:
    """Setting http.job_boards.<source>.enabled=false must disable every adapter."""
    from contextlib import ExitStack

    import job_hunter.sources.source_config as source_config

    for source_name, adapter_type in BOARD_REGISTRY.items():
        adapter = adapter_type()
        config = {"http": {"job_boards": {source_name: {"enabled": False}}}}
        module = inspect.getmodule(adapter_type)
        with ExitStack() as stack:
            # Adapters read config either directly (module-level get_api_config)
            # or via source_config.job_board_enabled — cover both.
            stack.enter_context(patch.object(source_config, "get_api_config", return_value=config))
            if hasattr(module, "get_api_config"):
                stack.enter_context(patch.object(module, "get_api_config", return_value=config))
            assert adapter.is_enabled(config) is False, f"{source_name} ignores enabled=false"


def test_region_specific_sources_skip_unsupported_countries() -> None:
    """No source may silently fall back to a wrong country for an unsupported
    region — each must return [] without any HTTP call."""
    from job_hunter.sources.boards.bayt import BaytSource
    from job_hunter.sources.boards.careerjet import CareerjetSource
    from job_hunter.sources.boards.gulftalent import GulfTalentSource
    from job_hunter.sources.boards.jobicy import JobicySource
    from job_hunter.sources.boards.jobstreet import JobStreetSource

    unsupported = SearchParams(
        region_key="sudan",
        country="SD",
        location="Khartoum",
        search_lang="en",
        job_titles=["Product Manager"],
    )
    careerjet_cfg = {"http": {"job_boards": {"careerjet": {"enabled": True, "affid": "x"}}}}

    for adapter, module_path, extra_cfg in (
        (CareerjetSource(), "job_hunter.sources.boards.careerjet", careerjet_cfg),
        (GulfTalentSource(), "job_hunter.sources.boards.gulftalent", None),
        (BaytSource(), "job_hunter.sources.boards.bayt", None),
        (JobStreetSource(), "job_hunter.sources.boards.jobstreet", None),
        (JobicySource(), "job_hunter.sources.boards.jobicy", None),
    ):
        patches = []
        if extra_cfg is not None:
            patches.append(patch(f"{module_path}.get_api_config", return_value=extra_cfg))
        with patch(f"{module_path}.requests", autospec=True) as mock_requests:
            mock_requests.get.side_effect = AssertionError(f"{adapter.source_name} must not call HTTP")
            for p in patches:
                p.start()
            try:
                assert adapter.fetch(unsupported) == [], f"{adapter.source_name} returned jobs for unsupported country"
            finally:
                for p in patches:
                    p.stop()
