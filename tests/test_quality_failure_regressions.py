"""One-stop regression suite: every critical quality-failure guard the pipeline
relies on to keep scraped candidates clean. Each test targets the exact guard
by name so a future regression here fails loudly and close to the cause,
rather than as a confusing downstream symptom.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from job_hunter.agent_context.batch import screen_candidate_batch
from job_hunter.pipeline.enrichment import drop_dead_urls_before_enrichment
from job_hunter.pipeline.stages.screening import screen_jobs_by_rules
from job_hunter.sources.jd_fetcher import _is_posting_inactive
from job_hunter.sources.policy import JobPolicy


def _job(**overrides) -> dict:
    values = {
        "title": "Product Manager",
        "company": "Acme",
        "url": "https://boards.greenhouse.io/acme/jobs/123",
        "location": "Berlin",
        "snippet": "Own the roadmap.",
        # Relative so the fixture never rots into stale_date territory.
        "posted_date_text": (date.today() - timedelta(days=2)).isoformat(),
    }
    values.update(overrides)
    return values


# ── 1. Excluded title ────────────────────────────────────────────────────────


def test_excluded_title_is_rejected() -> None:
    policy = JobPolicy({"exclusions": {"title_terms": ["intern"]}})
    reason = policy.rejection_reason(_job(title="Product Manager Intern"), ["Product Manager"])
    assert reason == "excluded_title"


# ── 2. Excluded company ──────────────────────────────────────────────────────


def test_excluded_company_is_rejected() -> None:
    policy = JobPolicy({"exclusions": {"companies": ["Blocked Co"]}})
    reason = policy.rejection_reason(_job(company="Blocked Co"), ["Product Manager"])
    assert reason == "excluded_company"


# ── 3. Excluded industry ─────────────────────────────────────────────────────


def test_excluded_industry_is_screened_out() -> None:
    config = {"exclusions": {"industries": ["gambling"]}, "regions": {}}
    job = _job(snippet="Join our gambling platform as a product lead.")
    kept, rejected = screen_jobs_by_rules([job], config)
    assert kept == []
    assert rejected[0]["_rejection_reason"] == "excluded_industry"


# ── 4. Wrong location ────────────────────────────────────────────────────────


def test_wrong_location_is_rejected() -> None:
    policy = JobPolicy({"exclusions": {}})
    region_config = {"country": "DE", "location": "Berlin"}
    assert policy.has_wrong_location(_job(location="Munich, Germany"), region_config)
    assert not policy.has_wrong_location(_job(location="Berlin, Germany"), region_config)


# ── 5. Remote restricted to wrong country ────────────────────────────────────


def test_remote_job_restricted_to_wrong_country_is_rejected() -> None:
    policy = JobPolicy({"exclusions": {}})
    region_config = {"country": "DE", "location": "Berlin"}
    job = _job(location="Remote", location_restrictions=["United States"])
    assert policy.has_incompatible_location_metadata(job, region_config)


# ── 6. Closed posting ────────────────────────────────────────────────────────


def test_closed_posting_text_is_detected() -> None:
    assert _is_posting_inactive("Thanks for your interest. This position has been filled.")
    assert not _is_posting_inactive("We are looking for a Product Manager to own the roadmap.")


def test_closed_posting_is_flagged_by_fetch_jd() -> None:
    from job_hunter.sources import jd_fetcher

    closed_html = "<html><body><p>This position has been filled. Thanks for applying.</p></body></html>"
    with patch.object(jd_fetcher, "_fetch_html", return_value=(closed_html, 200)):
        result = jd_fetcher.fetch_jd("https://example.com/jobs/123", use_llm=False)

    assert result is not None
    assert result["job_description_fetch_status"] == "position_closed"


# ── 6b. Contract/fixed-term roles — shared between both screening modes ──────


def test_contract_role_via_employment_type_field_is_rejected() -> None:
    """The structured employment_type field must be honored even with no matching snippet
    phrase — neither screening mode consulted this reliable ATS field before."""
    policy = JobPolicy({})
    job = _job(employment_type="Contract", snippet="Own the roadmap.")
    assert policy.rejection_reason(job, ["Product Manager"]) == "contract_role"


def test_contract_role_is_rejected_identically_in_both_screening_modes(tmp_path) -> None:
    """LLM-API mode (screen_jobs_by_rules) and agent mode (screen_candidate_batch) must
    agree on contract-role rejection — agent mode previously had no contract check at all."""
    import yaml

    job = _job(employment_type="Contract")

    kept, rejected = screen_jobs_by_rules([job], {"job_titles": ["Product Manager"]})
    assert kept == []
    assert rejected[0]["_rejection_reason"] == "contract_role"

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"job_titles": ["Product Manager"]}), encoding="utf-8"
    )
    batch = {"batch_number": 1, "batch_size": 15, "jobs": [{**job, "candidate_id": "cand_1"}]}
    result = screen_candidate_batch(batch, root=tmp_path)
    assert result["retained"] == []
    assert "contract_role" in result["skipped"][0]["reasons"]


# ── 6c. Title allow-list applied in LLM-API mode too ──────────────────────────


def test_title_allow_list_applies_in_llm_api_screening() -> None:
    """screen_jobs_by_rules must apply the configured job_titles allow-list, not just the
    excluded-terms deny-list — title_filters was previously hardcoded to []."""
    job = _job(title="Warehouse Associate")
    kept, rejected = screen_jobs_by_rules([job], {"job_titles": ["Product Manager"]})
    assert kept == []
    assert rejected[0]["_rejection_reason"] == "excluded_title"


# ── 7. Dead URL ───────────────────────────────────────────────────────────────


def test_dead_url_is_dropped_before_enrichment() -> None:
    jobs = [_job(url="https://example.com/alive"), _job(url="https://example.com/dead", company="Other")]

    def checker(url: str, _timeout: int) -> bool:
        return "alive" in url

    alive = drop_dead_urls_before_enrichment(
        jobs, {"http": {"url_verification": {"enabled": True}}}, url_checker=checker
    )
    assert [j["url"] for j in alive] == ["https://example.com/alive"]


# ── 8. Listing/search page URL ───────────────────────────────────────────────


def test_listing_page_url_is_not_a_valid_job_url() -> None:
    policy = JobPolicy({"exclusions": {}})
    assert not policy.is_valid_job_url("https://example.com/careers")
    assert not policy.is_valid_job_url("https://example.com/jobs")
    assert not policy.is_valid_job_url("https://example.com/")
    assert policy.is_valid_job_url("https://boards.greenhouse.io/acme/jobs/123456")


def test_greenhouse_listing_url_is_rejected_before_fetch() -> None:
    from job_hunter.sources._jd_ats import is_greenhouse_listing_url

    assert is_greenhouse_listing_url("https://boards.greenhouse.io/acme")
    assert not is_greenhouse_listing_url("https://boards.greenhouse.io/acme/jobs/123")


# ── 9. Duplicate canonical URL ───────────────────────────────────────────────


def test_duplicate_canonical_url_is_deduped() -> None:
    from job_hunter.sources.search import canonicalize_url

    a = canonicalize_url("https://boards.greenhouse.io/acme/jobs/123?utm_source=x")
    b = canonicalize_url("https://boards.greenhouse.io/acme/jobs/123/")
    assert a == b


# ── 10. Already processed URL ────────────────────────────────────────────────


def test_already_processed_url_is_filtered_out(tmp_path) -> None:
    import job_hunter.tracking.processed_urls as tracker
    from job_hunter.tracking.processed_urls import filter_new_jobs
    from job_hunter.tracking.repository import mark_urls_processed

    mark_urls_processed(tmp_path, {"https://example.com/already-seen"})
    with patch.object(tracker, "REPO_ROOT", tmp_path):
        new_jobs, existing_urls = filter_new_jobs(
            [
                _job(url="https://example.com/already-seen", company="Seen"),
                _job(url="https://example.com/brand-new", company="New"),
            ]
        )

    assert [j["company"] for j in new_jobs] == ["New"]
    assert existing_urls & {"https://example.com/already-seen", "https://example.com/already-seen/"}
