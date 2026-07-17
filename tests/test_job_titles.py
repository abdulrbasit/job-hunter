from __future__ import annotations

from job_hunter.core.job_titles import load_job_titles


def test_loads_non_empty_title_list() -> None:
    titles = load_job_titles()

    assert len(titles) > 20
    assert all(isinstance(t, str) and t.strip() for t in titles)


def test_includes_common_titles() -> None:
    titles = load_job_titles()

    assert "Product Manager" in titles
    assert "Software Engineer" in titles


def test_cache_returns_same_object() -> None:
    assert load_job_titles() is load_job_titles()


def test_titles_are_unique() -> None:
    titles = load_job_titles()

    assert len(titles) == len(set(titles))
