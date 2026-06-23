"""Tests for sources/ats_urls.py."""

from job_hunter.sources.ats_urls import (
    company_name_from_url,
    company_slug_from_url,
    detect_ats,
    extract_career_url,
)

# ── detect_ats ────────────────────────────────────────────────────────────────


def test_detect_greenhouse() -> None:
    assert detect_ats("boards.greenhouse.io/acme") == ("greenhouse", "acme")


def test_detect_greenhouse_with_https() -> None:
    assert detect_ats("https://boards.greenhouse.io/acme") == ("greenhouse", "acme")


def test_detect_job_boards_greenhouse() -> None:
    assert detect_ats("job-boards.greenhouse.io/acme") == ("greenhouse", "acme")


def test_detect_lever() -> None:
    assert detect_ats("jobs.lever.co/acme") == ("lever", "acme")


def test_detect_smartrecruiters() -> None:
    assert detect_ats("jobs.smartrecruiters.com/Acme") == ("smartrecruiters", "Acme")


def test_detect_workable() -> None:
    assert detect_ats("apply.workable.com/acme") == ("workable", "acme")


def test_detect_ashby() -> None:
    assert detect_ats("jobs.ashbyhq.com/acme") == ("ashby", "acme")


def test_detect_hibob() -> None:
    assert detect_ats("mycompany.careers.hibob.com") == ("hibob", "mycompany")


def test_detect_personio() -> None:
    assert detect_ats("mycompany.jobs.personio.de") == ("personio", "mycompany")


def test_detect_recruitee() -> None:
    assert detect_ats("mycompany.recruitee.com") == ("recruitee", "mycompany")


def test_detect_breezy() -> None:
    assert detect_ats("mycompany.breezy.hr") == ("breezy", "mycompany")


def test_detect_teamtailor() -> None:
    assert detect_ats("mycompany.teamtailor.com") == ("teamtailor", "mycompany")


def test_detect_workday() -> None:
    result = detect_ats("acme.myworkdayjobs.com/en-US/Careers")
    assert result is not None
    assert result[0] == "workday"


def test_detect_unknown_returns_none() -> None:
    assert detect_ats("careers.unknown-company.com") is None


# ── extract_career_url ────────────────────────────────────────────────────────


def test_extract_career_url_greenhouse() -> None:
    url = extract_career_url("https://boards.greenhouse.io/acme/jobs/12345")
    assert url == "boards.greenhouse.io/acme"


def test_extract_career_url_lever() -> None:
    url = extract_career_url("https://jobs.lever.co/acme/abc-123-def")
    assert url == "jobs.lever.co/acme"


def test_extract_career_url_unknown_returns_none() -> None:
    assert extract_career_url("https://careers.unknown.com/jobs/1") is None


# ── company_slug_from_url ─────────────────────────────────────────────────────


def test_company_slug_greenhouse() -> None:
    assert company_slug_from_url("boards.greenhouse.io/acme") == "acme"


def test_company_slug_lever() -> None:
    assert company_slug_from_url("jobs.lever.co/acme") == "acme"


def test_company_slug_workday_strips_host() -> None:
    slug = company_slug_from_url("acme.myworkdayjobs.com/en-US/Careers")
    assert slug == "acme"


# ── company_name_from_url ─────────────────────────────────────────────────────


def test_company_name_lever() -> None:
    assert company_name_from_url("jobs.lever.co/get-your-guide") == "Get Your Guide"


def test_company_name_unknown_returns_none() -> None:
    assert company_name_from_url("https://example.com") is None
