"""Tests for tracking/processed_urls.py — uses temp DB, no API calls."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import job_hunter.tracking.processed_urls as tracker
from job_hunter.tracking.processed_urls import filter_new_jobs, load_processed, mark_processed
from job_hunter.tracking.repository import get_all_known_urls, mark_urls_processed


def _with_tmp_root(tmp_path: Path):
    """Context patch to use tmp_path as REPO_ROOT for tracker functions."""
    return patch.object(tracker, "REPO_ROOT", tmp_path)


def test_load_processed_returns_empty_when_no_db(tmp_path: Path) -> None:
    with _with_tmp_root(tmp_path):
        urls = load_processed()
    assert urls == set()


def test_load_processed_returns_urls_from_db(tmp_path: Path) -> None:
    mark_urls_processed(tmp_path, {"https://a.com", "https://b.com"})
    with _with_tmp_root(tmp_path):
        urls = load_processed()
    assert "https://a.com" in urls or "https://a.com/" in urls
    assert "https://b.com" in urls or "https://b.com/" in urls


def test_save_processed_inserts_urls(tmp_path: Path) -> None:
    with _with_tmp_root(tmp_path):
        from job_hunter.tracking.processed_urls import save_processed

        save_processed({"https://b.com", "https://a.com"})
    known = get_all_known_urls(tmp_path)
    assert len(known) > 0


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    urls = {"https://x.com/job/1", "https://y.com/job/2"}
    mark_urls_processed(tmp_path, urls)
    with _with_tmp_root(tmp_path):
        reloaded = load_processed()
    for u in urls:
        assert any(u in r for r in reloaded)


def test_filter_new_jobs_removes_already_processed(tmp_path: Path) -> None:
    mark_urls_processed(tmp_path, {"https://seen.com"})
    jobs = [
        {"title": "PM", "company": "Seen", "url": "https://seen.com"},
        {"title": "PO", "company": "New", "url": "https://new.com"},
    ]
    with _with_tmp_root(tmp_path):
        new_jobs, existing_urls = filter_new_jobs(jobs)
    assert len(new_jobs) == 1
    assert new_jobs[0]["url"] == "https://new.com"
    assert any("seen.com" in u for u in existing_urls)


def test_filter_new_jobs_all_new_when_no_tracker(tmp_path: Path) -> None:
    with _with_tmp_root(tmp_path):
        new_jobs, existing_urls = filter_new_jobs([{"title": "PM", "company": "X", "url": "https://x.com"}])
    assert len(new_jobs) == 1
    assert existing_urls == set()


def test_mark_processed_merges_with_existing(tmp_path: Path) -> None:
    mark_urls_processed(tmp_path, {"https://old.com"})
    jobs = [{"title": "PM", "company": "New", "url": "https://new.com"}]
    with _with_tmp_root(tmp_path):
        mark_processed(jobs, {"https://old.com"})
        reloaded = load_processed()
    assert any("old.com" in u for u in reloaded)
    assert any("new.com" in u for u in reloaded)


def test_mark_processed_deduplicates(tmp_path: Path) -> None:
    mark_urls_processed(tmp_path, {"https://a.com"})
    jobs = [
        {"title": "PM", "company": "A", "url": "https://a.com"},
        {"title": "PO", "company": "B", "url": "https://b.com"},
    ]
    with _with_tmp_root(tmp_path):
        mark_processed(jobs, {"https://a.com"})
        reloaded = load_processed()
    assert any("a.com" in u for u in reloaded)
    assert any("b.com" in u for u in reloaded)


def test_filter_new_jobs_does_not_skip_by_title_key(tmp_path: Path) -> None:
    # Title-key dedup removed from persistent tracking — same title at same company is not blocked
    jobs = [
        {"title": "Product Manager", "company": "TestCo", "url": "https://testco.com/job/99"},
    ]
    with _with_tmp_root(tmp_path):
        new_jobs, _ = filter_new_jobs(jobs)
    assert len(new_jobs) == 1
