from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from job_hunter.companies.classification import classify_company
from job_hunter.companies.store import candidate_companies, ensure_seeded, query_page
from job_hunter.config.service import apply_onboarding_prefs
from job_hunter.models import CompanyType, FundingStage, JobPosting, SearchParams
from job_hunter.sources.boards.start_munich import StartMunichSource
from job_hunter.sources.boards.startup_jobs import StartupJobsSource
from job_hunter.sources.boards.yc_jobs import YCJobsSource
from job_hunter.sources.orchestrator import deduplicate_company_titles
from job_hunter.tracking.repository import get_jobs_page, insert_jobs
from scripts import import_startup_companies


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def _params(country: str = "DE") -> SearchParams:
    return SearchParams(
        region_key="primary",
        country=country,
        location="Munich" if country == "DE" else "New York",
        search_lang="en",
        job_titles=["Product Manager"],
    )


def test_company_types_and_conservative_classification() -> None:
    assert CompanyType.STARTUP == "startup"
    assert FundingStage.SERIES_A == "series_a"
    assert classify_company(company_type="enterprise", funding_stage="seed") == CompanyType.ENTERPRISE
    assert classify_company(status="public", headcount=20) == CompanyType.ENTERPRISE
    assert classify_company(funding_stage="series_b") == CompanyType.SCALEUP
    assert classify_company(funding_stage="seed") == CompanyType.STARTUP
    assert classify_company(ecosystem="yc", status="active") == CompanyType.STARTUP
    assert classify_company(headcount=12) == CompanyType.UNKNOWN


def test_models_carry_startup_and_unknown_experience_metadata() -> None:
    job = JobPosting(
        title="Product Manager",
        company="Acme",
        url="https://example.com/job",
        company_type="startup",
        funding_stage="seed",
        experience_unknown=True,
    )
    assert job.company_type is CompanyType.STARTUP
    assert job.funding_stage is FundingStage.SEED
    assert job.experience_unknown is True


def test_onboarding_toggle_is_one_config_choice() -> None:
    enabled = apply_onboarding_prefs({}, {"include_startups": True})
    assert enabled["companies"]["include_startups"] is True
    assert "sources" not in enabled


def test_company_store_migrates_and_filters_metadata(tmp_path: Path) -> None:
    ensure_seeded(tmp_path)
    db = tmp_path / "outputs" / "state" / "companies.db"
    with sqlite3.connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(companies)")}
        conn.execute(
            """UPDATE companies SET company_type='startup', funding_stage='seed', enabled=0
               WHERE id=(SELECT id FROM companies WHERE country='DE' LIMIT 1)"""
        )
    assert {"company_type", "funding_stage"} <= columns
    page = query_page(tmp_path, source="catalog", company_type="startup", funding_stage="seed")
    assert page["total"] == 1
    automatic = candidate_companies(tmp_path, countries=["DE"], include_startups=True, startup_cap=100)
    assert any(row["company_type"] == "startup" for row in automatic)


@pytest.mark.parametrize(
    ("source", "body", "expected_company"),
    [
        (
            StartupJobsSource(),
            """<rss><channel><item><title>Product Manager at Acme</title>
            <link>https://startup.jobs/acme-product-manager</link>
            <description>Berlin startup role</description><author>Acme</author></item></channel></rss>""",
            "Acme",
        ),
        (
            YCJobsSource(),
            """<article><a href='/companies/acme/jobs/1-product-manager'><h3>Product Manager</h3></a>
            <p class='company'>Acme</p><span>New York, US</span></article>""",
            "Acme",
        ),
        (
            StartMunichSource(),
            """<article><a href='https://jobs.startmunich.de/companies/acme/jobs/1'><h3>Product Manager</h3></a>
            <p class='company'>Acme</p><span>Munich, Germany</span></article>""",
            "Acme",
        ),
    ],
)
def test_startup_adapters_parse_bounded_public_listings(monkeypatch, source, body, expected_company) -> None:
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _Response(body))
    jobs = source.fetch(_params("DE" if source.source_name == "start_munich" else "US"))
    assert len(jobs) == 1
    assert jobs[0].company == expected_company
    assert jobs[0].company_type is CompanyType.STARTUP
    assert jobs[0].source_url


def test_start_munich_is_germany_only() -> None:
    assert StartMunichSource().supports_country("DE")
    assert not StartMunichSource().supports_country("US")


def test_same_company_fuzzy_dedup_never_crosses_company_boundary() -> None:
    jobs = [
        JobPosting(title="Senior Product Manager", company="Acme, Inc.", url="https://one.test/1"),
        JobPosting(title="Senior Product Manager (m/f/d)", company="ACME", url="https://two.test/2"),
        JobPosting(title="Senior Product Manager", company="Other", url="https://three.test/3"),
    ]
    deduped = deduplicate_company_titles(jobs)
    assert [job.company for job in deduped] == ["Acme, Inc.", "Other"]


def test_job_metadata_persists_and_feed_filters(tmp_path: Path) -> None:
    insert_jobs(
        tmp_path,
        [
            {
                "title": "Product Manager",
                "company": "Acme",
                "url": "https://example.com/jobs/1",
                "company_type": "startup",
                "funding_stage": "seed",
                "experience_unknown": True,
                "source": "Startup.jobs",
                "source_url": "https://startup.jobs/feeds/jobs",
            }
        ],
    )
    rows, total = get_jobs_page(tmp_path, statuses=("candidate",), company_type="startup")
    assert total == 1
    assert rows[0]["funding_stage"] == "seed"
    assert rows[0]["experience_unknown"] == 1
    assert rows[0]["source_url"] == "https://startup.jobs/feeds/jobs"


def test_maintainer_importer_writes_only_package_shards(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "package-data"
    data_dir.mkdir()
    (data_dir / "DE.jsonl").write_text("", encoding="utf-8")
    source = tmp_path / "startups.csv"
    source.write_text(
        "name,career_url,country,industry,funding_stage\nAcme,https://acme.test/careers,DE,software_it,seed\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(import_startup_companies, "DATA_DIR", data_dir)
    assert import_startup_companies.import_file(source) == 1
    row = (data_dir / "DE.jsonl").read_text(encoding="utf-8")
    assert '"company_type":"startup"' in row
    assert not (tmp_path / "config").exists()


def test_dashboard_exposes_startup_and_unknown_experience_controls() -> None:
    web = Path("job_hunter/ux/web")
    html = (web / "dashboard.html").read_text(encoding="utf-8")
    javascript = (web / "dashboard.js").read_text(encoding="utf-8")
    assert 'id="include-startups"' in html
    assert 'id="candidate-company-type"' in html
    assert 'id="catalog-funding-stage-filter"' in html
    assert "experience unknown" in javascript
