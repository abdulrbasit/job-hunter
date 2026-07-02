"""Cross-adapter contracts every registered JobSourceAdapter must satisfy.

See job_hunter/sources/base.py's module docstring for the source of truth:
  - fetch() must NEVER raise. Return [] on any error and log at WARNING.
  - All returned JobPosting objects must have url, title, company, source set.
  - is_enabled() must honor the api_config it's given, not just global state.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from job_hunter.models import SearchParams
from job_hunter.sources.boards import BOARD_REGISTRY

# jsearch gates on RapidAPI key presence (an instance secret), not a
# job_boards.<name>.enabled config flag — it has no api_config-driven toggle to test.
_NO_CONFIG_TOGGLE = {"jsearch"}
# careerjet additionally requires a configured affiliate id, so it is not
# enabled-by-default even with an otherwise-empty api_config.
_NOT_ENABLED_BY_DEFAULT = {"careerjet"}


def _params() -> SearchParams:
    return SearchParams(
        region_key="test",
        country="DE",
        location="Berlin",
        search_lang="en",
        job_titles=["Product Manager"],
    )


@pytest.mark.parametrize("name,cls", sorted(BOARD_REGISTRY.items()))
def test_fetch_never_raises_even_when_fetch_impl_blows_up(name, cls) -> None:
    adapter = cls()
    with patch.object(cls, "_fetch", side_effect=RuntimeError("boom")):
        assert adapter.fetch(_params()) == []


@pytest.mark.parametrize("name,cls", sorted((n, c) for n, c in BOARD_REGISTRY.items() if n not in _NO_CONFIG_TOGGLE))
def test_is_enabled_respects_supplied_api_config(name, cls) -> None:
    adapter = cls()
    disabled = {"http": {"job_boards": {name: {"enabled": False}}}}
    assert adapter.is_enabled(disabled) is False


@pytest.mark.parametrize(
    "name,cls",
    sorted((n, c) for n, c in BOARD_REGISTRY.items() if n not in _NO_CONFIG_TOGGLE | _NOT_ENABLED_BY_DEFAULT),
)
def test_is_enabled_defaults_true_when_config_says_nothing(name, cls) -> None:
    adapter = cls()
    assert adapter.is_enabled({}) is True


def test_job_posting_requires_url_title_company() -> None:
    """Structural backing for "returned postings have url/title/company/source":
    JobPosting's required fields make it impossible for a _fetch() implementation
    to construct a posting that fetch() could return without them."""
    from job_hunter.models import JobPosting

    required = {name for name, field in JobPosting.model_fields.items() if field.is_required()}
    assert {"title", "company", "url"} <= required
