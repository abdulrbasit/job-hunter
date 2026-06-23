"""Tests for tracking/tracker.py — uses temp files, no API calls."""

from unittest.mock import patch

import yaml

from job_hunter.tracking import tracker


def test_load_processed_returns_empty_when_no_file(tmp_path) -> None:
    with patch.object(tracker, "TRACKER_FILE", str(tmp_path / "discovered_urls.yml")):
        urls = tracker.load_processed()
    assert urls == set()


def test_load_processed_returns_urls_from_file(tmp_path) -> None:
    f = tmp_path / "discovered_urls.yml"
    f.write_text(yaml.dump({"discovered": ["https://a.com", "https://b.com"]}))
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        urls = tracker.load_processed()
    assert urls == {"https://a.com/", "https://b.com/"}


def test_load_processed_handles_empty_file(tmp_path) -> None:
    f = tmp_path / "discovered_urls.yml"
    f.write_text("")
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        urls = tracker.load_processed()
    assert urls == set()


def test_save_processed_writes_sorted_urls(tmp_path) -> None:
    f = tmp_path / "discovered_urls.yml"
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        tracker.save_processed({"https://b.com", "https://a.com"})
    data = yaml.safe_load(f.read_text())
    assert data["discovered"] == ["https://a.com/", "https://b.com/"]


def test_save_and_reload_roundtrip(tmp_path) -> None:
    f = tmp_path / "discovered_urls.yml"
    urls = {"https://x.com/job/1", "https://y.com/job/2"}
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        tracker.save_processed(urls)
        reloaded_urls = tracker.load_processed()
    assert reloaded_urls == urls


def test_filter_new_jobs_removes_already_processed(tmp_path) -> None:
    f = tmp_path / "discovered_urls.yml"
    f.write_text(yaml.dump({"discovered": ["https://seen.com"]}))
    jobs = [
        {"title": "PM", "company": "Seen", "url": "https://seen.com"},
        {"title": "PO", "company": "New", "url": "https://new.com"},
    ]
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        new_jobs, existing_urls = tracker.filter_new_jobs(jobs)
    assert len(new_jobs) == 1
    assert new_jobs[0]["url"] == "https://new.com"
    assert "https://seen.com/" in existing_urls


def test_filter_new_jobs_all_new_when_no_tracker(tmp_path) -> None:
    with patch.object(tracker, "TRACKER_FILE", str(tmp_path / "discovered_urls.yml")):
        new_jobs, existing_urls = tracker.filter_new_jobs(
            [
                {"title": "PM", "company": "X", "url": "https://x.com"},
            ]
        )
    assert len(new_jobs) == 1
    assert existing_urls == set()


def test_mark_processed_merges_with_existing(tmp_path) -> None:
    f = tmp_path / "discovered_urls.yml"
    existing_urls = {"https://old.com"}
    jobs = [{"title": "PM", "company": "New", "url": "https://new.com"}]
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        tracker.mark_processed(jobs, existing_urls)
        reloaded_urls = tracker.load_processed()
    assert reloaded_urls == {"https://old.com/", "https://new.com/"}


def test_mark_processed_deduplicates(tmp_path) -> None:
    f = tmp_path / "discovered_urls.yml"
    existing_urls = {"https://a.com"}
    jobs = [
        {"title": "PM", "company": "A", "url": "https://a.com"},
        {"title": "PO", "company": "B", "url": "https://b.com"},
    ]
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        tracker.mark_processed(jobs, existing_urls)
        reloaded_urls = tracker.load_processed()
    assert reloaded_urls == {"https://a.com/", "https://b.com/"}


def test_filter_new_jobs_does_not_skip_by_title_key(tmp_path) -> None:
    # Title-key dedup removed from persistent tracking — same title at same company is not blocked
    f = tmp_path / "discovered_urls.yml"
    f.write_text(yaml.dump({"applied_titles": ["testco::product manager"]}))
    jobs = [
        {"title": "Product Manager", "company": "TestCo", "url": "https://testco.com/job/99"},
    ]
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        new_jobs, _ = tracker.filter_new_jobs(jobs)
    assert len(new_jobs) == 1
