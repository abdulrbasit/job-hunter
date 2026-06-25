"""Tests for pipeline/tailorer.py — all LLM calls are mocked."""

from unittest.mock import MagicMock, patch

from job_hunter.pipeline import tailorer

MATCH = {
    "job": {
        "title": "Product Manager",
        "company": "TestCo",
        "snippet": "PM role requiring agile, roadmapping.",
    },
    "matched_keywords": ["agile", "roadmapping"],
    "gaps": ["automotive"],
    "score": 85,
}

SAMPLE_LATEX = r"""\documentclass{altacv}
\begin{document}
\section{Experience}
\cvevent{Product Owner}{ExampleCo}{2021--Present}{Target City}
\begin{itemize}
\item Led platform product strategy
\end{itemize}
\end{document}"""


def test_tailor_returns_llm_output(mock_llm_client) -> None:
    with patch("job_hunter.pipeline.tailorer.get_llm_client", return_value=mock_llm_client(SAMPLE_LATEX)):
        result = tailorer.tailor(MATCH)
    assert result == SAMPLE_LATEX


def test_tailor_output_starts_with_backslash(mock_llm_client) -> None:
    with patch("job_hunter.pipeline.tailorer.get_llm_client", return_value=mock_llm_client(SAMPLE_LATEX)):
        result = tailorer.tailor(MATCH)
    assert result.startswith("\\")


def test_tailor_falls_back_to_base_tex_on_api_error() -> None:
    mock = MagicMock()
    mock.complete.side_effect = Exception("API down")
    with patch("job_hunter.pipeline.tailorer.get_llm_client", return_value=mock):
        result = tailorer.tailor(MATCH)
    assert result == tailorer._get_base_tex()


def test_tailor_returns_non_latex_response_unchanged(mock_llm_client) -> None:
    with patch(
        "job_hunter.pipeline.tailorer.get_llm_client",
        return_value=mock_llm_client("plain text response"),
    ):
        result = tailorer.tailor(MATCH)
    assert result == "plain text response"


def test_tailor_passes_keywords_and_gaps_in_prompt() -> None:
    captured = {}

    def capture_complete(req, **kwargs):
        captured["user"] = req.prompt
        return MagicMock(content=SAMPLE_LATEX)

    mock = MagicMock()
    mock.complete.side_effect = capture_complete

    with patch("job_hunter.pipeline.tailorer.get_llm_client", return_value=mock):
        tailorer.tailor(MATCH)

    assert "agile" in captured["user"]
    assert "automotive" in captured["user"]


def test_tailor_includes_project_rules_and_story_bank_for_active_projects() -> None:
    captured = {}

    def capture_complete(req, **kwargs):
        captured["user"] = req.prompt
        captured["system"] = req.system or ""
        return MagicMock(content=SAMPLE_LATEX)

    tex_with_projects = r"""\documentclass{altacv}
\begin{document}
\cvsection{Technical Projects}
\cvevent{Project}{Course}{2026}{}
\begin{itemize}
\item Existing project bullet
\end{itemize}
\end{document}"""

    mock = MagicMock()
    mock.complete.side_effect = capture_complete

    with (
        patch.object(tailorer, "_get_base_tex", return_value=tex_with_projects),
        patch.object(
            tailorer,
            "_load_profile_text",
            side_effect=lambda k, d, **kw: "### MS-01 — Digital Factory story" if k == "story_bank" else "",
        ),
        patch("job_hunter.pipeline.tailorer.get_llm_client", return_value=mock),
    ):
        tailorer.tailor(MATCH)

    # Project rules and story bank are now in the system prompt (cached prefix).
    assert "Include at most 4 projects total" in captured["system"]
    assert "Never exceed 5 bullets" in captured["system"]
    assert "Do not create a third page" in captured["system"]
    assert "MS-01" in captured["system"]


def test_tailor_disables_project_tailoring_when_section_is_commented() -> None:
    captured = {}

    def capture_complete(req, **kwargs):
        captured["user"] = req.prompt
        captured["system"] = req.system or ""
        return MagicMock(content=SAMPLE_LATEX)

    tex_with_commented_projects = r"""\documentclass{altacv}
\begin{document}
% \cvsection{Projects}
% \cvevent{Project}{Course}{2026}{}
\end{document}"""

    mock = MagicMock()
    mock.complete.side_effect = capture_complete

    with (
        patch.object(tailorer, "_get_base_tex", return_value=tex_with_commented_projects),
        patch.object(
            tailorer,
            "_load_profile_text",
            side_effect=lambda k, d, **kw: "### MS-01 — Digital Factory story" if k == "story_bank" else "",
        ),
        patch("job_hunter.pipeline.tailorer.get_llm_client", return_value=mock),
    ):
        tailorer.tailor(MATCH)

    # Project rules are now in the system prompt (cached prefix).
    assert "No active Projects/Technical Projects section exists" in captured["system"]
    assert "Do not add, uncomment, or tailor project content" in captured["system"]
