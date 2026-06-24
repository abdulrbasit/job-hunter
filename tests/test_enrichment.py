from __future__ import annotations

from job_hunter.pipeline.enrichment import (
    JD_STATUS_FETCH_FAILED,
    JD_STATUS_FULL,
    JD_STATUS_PAGE_NOISE,
    JD_STATUS_THIN,
    classify_jd_snippet,
    enrich_snippets,
)


def test_classify_jd_snippet_statuses() -> None:
    assert classify_jd_snippet("Product Manager @ Acme") == JD_STATUS_THIN
    assert (
        classify_jd_snippet("Create a Job Alert Current openings View all jobs Search jobs Cookie Privacy Policy " * 80)
        == JD_STATUS_PAGE_NOISE
    )
    assert (
        classify_jd_snippet(
            "Responsibilities include roadmap ownership. Requirements include product discovery experience. " * 20
        )
        == JD_STATUS_FULL
    )


def test_enrich_snippets_upgrades_web_search_candidate_and_preserves_search_snippet() -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "Acme",
            "url": "https://jobs.smartrecruiters.com/acme/123-product-manager",
            "snippet": "Short LLM-written summary.",
            "source": "web-search",
        }
    ]

    def fetcher(_url: str, **_kwargs) -> dict:
        return {
            "title": "Senior Product Manager",
            "company": "Acme",
            "url": "https://jobs.smartrecruiters.com/acme/123-product-manager",
            "location": "Berlin",
            "snippet": (
                "Responsibilities include roadmap ownership. Requirements include product discovery experience. " * 20
            ),
            "source": "smartrecruiters_api",
        }

    enriched = enrich_snippets(jobs, {"http": {"jd_enrichment": {"max_workers": 1}}}, fetcher=fetcher)

    assert enriched[0]["jd_status"] == JD_STATUS_FULL
    assert enriched[0]["source"] == "web-search"
    assert enriched[0]["enrichment_source"] == "smartrecruiters_api"
    assert enriched[0]["search_snippet"] == "Short LLM-written summary."
    assert enriched[0]["title"] == "Senior Product Manager"
    assert "product discovery" in enriched[0]["snippet"]


def test_enrich_snippets_marks_failed_thin_candidate() -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "Acme",
            "url": "https://jobs.ashbyhq.com/acme/job-123",
            "snippet": "Product Manager @ Acme",
            "source": "direct_link",
        }
    ]

    enriched = enrich_snippets(
        jobs,
        {"http": {"jd_enrichment": {"max_workers": 1}}},
        fetcher=lambda _url: None,
    )

    assert enriched[0]["jd_status"] == JD_STATUS_FETCH_FAILED
    assert enriched[0]["snippet"] == "Product Manager @ Acme"
