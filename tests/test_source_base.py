from __future__ import annotations

import pytest

from job_hunter.models import SearchParams
from job_hunter.sources._base import JobSourceAdapter


def test_cannot_instantiate_abstract() -> None:
    abstract_source: type = JobSourceAdapter
    with pytest.raises(TypeError):
        abstract_source()


def test_concrete_subclass_instantiates() -> None:
    class MySource(JobSourceAdapter):
        @property
        def source_name(self) -> str:
            return "my_source"

        def _fetch(self, params: SearchParams) -> list:
            return []

    src = MySource()
    assert src.name == "my_source"
    params = SearchParams(region_key="test", country="DE", location="Berlin", search_lang="", job_titles=[])
    assert src.fetch(params) == []


def test_is_enabled_defaults_true() -> None:
    class AnotherSource(JobSourceAdapter):
        @property
        def source_name(self) -> str:
            return "another"

        def _fetch(self, params: SearchParams) -> list:
            return []

    src = AnotherSource()
    assert src.is_enabled({}) is True
    assert src.is_enabled({"some_key": "some_val"}) is True
