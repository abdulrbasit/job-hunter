"""Tests for sources.jd_fetcher."""

from unittest.mock import MagicMock, patch

import pytest

from job_hunter.sources import jd_fetcher
from job_hunter.sources.ats_urls import company_name_from_url

SAMPLE_URL = "https://boards.greenhouse.io/testcorp/jobs/12345"

# ~400 chars of body text — sufficient to skip the Playwright trigger
RICH_HTML = (
    "<html><body>"
    "<h1>Senior Product Manager</h1>" + "<p>We are looking for an experienced Senior Product Manager to join our team. "
    "You will define product strategy, collaborate with engineers and designers, "
    "and deliver measurable user value. Requirements: 3+ years PM experience, "
    "strong data-driven decision making, excellent stakeholder communication.</p>" + "</body></html>"
)

# Almost no text — triggers the Playwright fallback path (but not empty, to allow LLM fallback)
SPARSE_HTML = "<html><body><div id='root'><p>Loading job...</p></div></body></html>"

LLM_JSON = '{"title": "Senior Product Manager", "company": "TestCorp", "description": "Full job description."}'


class TestCompanyNameFromUrl:
    @pytest.mark.parametrize(
        "url, expected",
        [
            ("https://boards.greenhouse.io/testcorp/jobs/1", "Testcorp"),
            ("https://jobs.lever.co/mycompany/abc", "Mycompany"),
            ("https://myco.jobs.personio.de/job/1", "Myco"),
            ("https://careers.bigcorp.com/jobs/456", "Bigcorp"),
            ("https://boards.greenhouse.io/my-cool-corp/jobs/1", "My Cool Corp"),
            ("https://www.example.com/jobs", None),
        ],
    )
    def test_company_name_from_url(self, url, expected) -> None:
        assert company_name_from_url(url) == expected


def _jd_llm_client(text: str) -> MagicMock:
    """jd_fetcher calls client.complete() with old-style kwargs; it expects a plain str back."""
    mock = MagicMock()
    mock.complete.return_value = text
    return mock


class TestFetchJd:
    def test_returns_job_dict_on_success(self) -> None:
        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(RICH_HTML, 200)),
            patch(
                "job_hunter.sources.jd_fetcher.get_llm_client",
                return_value=_jd_llm_client(LLM_JSON),
            ),
        ):
            result = jd_fetcher.fetch_jd(SAMPLE_URL)

        assert result is not None
        assert result["url"] == SAMPLE_URL
        assert result["title"] == "Senior Product Manager"
        assert result["company"] == "TestCorp"
        assert result["snippet"] == "Full job description."
        assert result["source"] == "direct_link"

    def test_accepts_fenced_json_with_preamble(self) -> None:
        raw = f"Parsed:\n```json\n{LLM_JSON}\n```"
        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(RICH_HTML, 200)),
            patch("job_hunter.sources.jd_fetcher.get_llm_client", return_value=_jd_llm_client(raw)),
        ):
            result = jd_fetcher.fetch_jd(SAMPLE_URL)

        assert result is not None
        assert result["title"] == "Senior Product Manager"
        assert result["company"] == "TestCorp"

    def test_accepts_json_with_trailing_extra_data(self) -> None:
        raw = f'{LLM_JSON}\n{{"note": "ignored trailing object"}}'
        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(RICH_HTML, 200)),
            patch("job_hunter.sources.jd_fetcher.get_llm_client", return_value=_jd_llm_client(raw)),
        ):
            result = jd_fetcher.fetch_jd(
                "https://jobs.infineon.com/careers/job/563808970725337?domain=infineon.com&hl=en"
            )

        assert result is not None
        assert result["title"] == "Senior Product Manager"
        assert result["company"] == "TestCorp"

    def test_returns_none_when_fetch_fails(self) -> None:
        with patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(None, None)):
            assert jd_fetcher.fetch_jd(SAMPLE_URL) is None

    def test_playwright_called_on_sparse_html(self) -> None:
        pw_text = "Full rendered job description from JavaScript. " * 20

        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(SPARSE_HTML, 200)),
            patch("job_hunter.sources.jd_fetcher._fetch_playwright", return_value=pw_text) as mock_pw,
            patch(
                "job_hunter.sources.jd_fetcher.get_llm_client",
                return_value=_jd_llm_client(LLM_JSON),
            ),
        ):
            result = jd_fetcher.fetch_jd(SAMPLE_URL)

        assert mock_pw.called
        assert mock_pw.call_args[0][0] == SAMPLE_URL
        assert result is not None

    def test_playwright_not_called_on_rich_html(self) -> None:
        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(RICH_HTML, 200)),
            patch("job_hunter.sources.jd_fetcher._fetch_playwright") as mock_pw,
            patch(
                "job_hunter.sources.jd_fetcher.get_llm_client",
                return_value=_jd_llm_client(LLM_JSON),
            ),
        ):
            jd_fetcher.fetch_jd(SAMPLE_URL)

        mock_pw.assert_not_called()

    def test_uses_plain_text_fallback_when_llm_returns_no_description(self) -> None:
        no_desc = '{"title": "PM", "company": "Corp", "description": null}'
        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(RICH_HTML, 200)),
            patch("job_hunter.sources.jd_fetcher.get_llm_client", return_value=_jd_llm_client(no_desc)),
        ):
            result = jd_fetcher.fetch_jd(SAMPLE_URL)

        assert result is not None
        assert len(result["snippet"]) > 0

    def test_handles_list_shaped_llm_result(self) -> None:
        extracted = [
            {
                "title": "Technical Product Owner",
                "company": "StepStone",
                "description": "Full StepStone job description.",
            }
        ]

        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(RICH_HTML, 200)),
            patch("job_hunter.sources.jd_fetcher._llm_extract", return_value=extracted),
        ):
            result = jd_fetcher.fetch_jd("https://www.stepstone.de/jobs/technical-product-owner/in-berlin")

        assert result is not None
        assert result["title"] == "Technical Product Owner"
        assert result["company"] == "StepStone"
        assert result["snippet"] == "Full StepStone job description."

    def test_uses_guessed_company_when_llm_returns_null(self, mock_llm_client) -> None:
        no_company = '{"title": "PM", "company": null, "description": "desc"}'
        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(RICH_HTML, 200)),
            patch(
                "job_hunter.sources.jd_fetcher.get_llm_client",
                return_value=mock_llm_client(no_company),
            ),
        ):
            result = jd_fetcher.fetch_jd(SAMPLE_URL)

        assert result is not None
        # URL is boards.greenhouse.io/testcorp/... → guessed as "Testcorp"
        assert result["company"] == "Testcorp"

    def test_keeps_richer_playwright_text_over_sparse_static(self) -> None:
        pw_text = "Detailed description from JS rendering. " * 30

        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(SPARSE_HTML, 200)),
            patch("job_hunter.sources.jd_fetcher._fetch_playwright", return_value=pw_text),
            patch("job_hunter.sources.jd_fetcher._llm_extract", return_value={}) as mock_extract,
        ):
            jd_fetcher.fetch_jd(SAMPLE_URL)

        # LLM should have received the longer playwright text, not the sparse static text
        called_text = mock_extract.call_args[0][0]
        assert len(called_text) > jd_fetcher._MIN_TEXT_LENGTH

    def test_keeps_static_text_when_playwright_returns_none(self) -> None:
        # Playwright unavailable — LLM should receive whatever static text exists
        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(SPARSE_HTML, 200)),
            patch("job_hunter.sources.jd_fetcher._fetch_playwright", return_value=None),
            patch("job_hunter.sources.jd_fetcher._llm_extract", return_value={}) as mock_extract,
        ):
            jd_fetcher.fetch_jd(SAMPLE_URL)

        # LLM should still be called (with the sparse static text as fallback)
        mock_extract.assert_called_once()

    def test_can_skip_llm_for_snippet_enrichment(self) -> None:
        with (
            patch("job_hunter.sources.jd_fetcher._fetch_html", return_value=(RICH_HTML, 200)),
            patch("job_hunter.sources.jd_fetcher._llm_extract") as mock_extract,
        ):
            result = jd_fetcher.fetch_jd(SAMPLE_URL, use_llm=False)

        mock_extract.assert_not_called()
        assert result is not None
        assert result["company"] == "Testcorp"
        assert "Senior Product Manager" in result["snippet"]


class TestFetchPlaywright:
    def test_returns_none_when_playwright_not_installed(self) -> None:
        # Simulate playwright being absent by setting its entry in sys.modules to None,
        # which causes Python to raise ImportError on the internal import.
        with patch.dict("sys.modules", {"playwright.sync_api": None}):
            result = jd_fetcher._fetch_playwright("https://example.com/job")
        assert result is None

    def test_returns_none_on_browser_exception(self) -> None:
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(side_effect=Exception("browser crashed"))
        mock_context.__exit__ = MagicMock(return_value=False)

        mock_sync_playwright = MagicMock(return_value=mock_context)

        with patch.dict("sys.modules", {"playwright.sync_api": MagicMock(sync_playwright=mock_sync_playwright)}):
            result = jd_fetcher._fetch_playwright("https://example.com/job")
        assert result is None
