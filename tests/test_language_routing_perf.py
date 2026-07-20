"""Phase 4/4 optimize — the prompt-caching contract for language routing.

`pipeline/tailorer.py::tailor()` and `pipeline/cover_writer.py::write_cover()` both run
with `cache_system=True`: Anthropic (and equivalent providers) cache the system-prompt
prefix across calls in a run, which only pays off if that prefix is byte-identical
across jobs. Routing must never let a per-job value (job language, translation
instructions) leak into the system prompt — everything variable belongs in the user
prompt. This guards that contract across the full language matrix, not just one
language pair, since a single spot-check wouldn't catch a language-keyed cache key
accidentally sneaking into the system assembly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from job_hunter.pipeline import cover_writer, tailorer

_LANGUAGES = ("en", "de", "fr", "ja")

_SAMPLE_TEX = r"""\documentclass{altacv}
\begin{document}
\section{Experience}
\cvevent{Product Owner}{ExampleCo}{2021--Present}{Target City}
\begin{itemize}
\item Led platform product strategy
\end{itemize}
\end{document}"""

_MATCH = {
    "job": {
        "title": "Product Manager",
        "company": "TestCo",
        "url": "https://testco.com/job",
        "snippet": "PM role at TestCo.",
        "posted_date_text": "2026-04-01",
    },
    "matched_keywords": ["agile"],
    "gaps": [],
    "score": 85,
}

_COVER_CONFIG = {
    "header": {"include_date": False, "salutation": "Dear Hiring Manager,"},
    "closing": {"format": "Best regards,\nCandidate Name"},
}


def _capture_tailor_prompts(target: str) -> dict:
    tailorer._get_base_tex.cache_clear()
    captured = {}

    def capture_complete(req, **kwargs):
        captured["system"] = req.system or ""
        captured["user"] = req.prompt
        return MagicMock(content=_SAMPLE_TEX)

    mock = MagicMock()
    mock.complete.side_effect = capture_complete
    with patch("job_hunter.pipeline.tailorer.get_llm_client", return_value=mock):
        tailorer.tailor({**_MATCH, "output_language": target})
    tailorer._get_base_tex.cache_clear()
    return captured


def _capture_cover_prompts(target: str, tmp_path) -> dict:
    captured = {}

    def capture_complete(req, **kwargs):
        captured["system"] = req.system or ""
        captured["user"] = req.prompt
        return MagicMock(content="Body text for the cover letter, four sentences long here.")

    mock = MagicMock()
    mock.complete.side_effect = capture_complete
    with patch("job_hunter.pipeline.cover_writer.get_llm_client", return_value=mock):
        cover_writer.write_cover({**_MATCH, "output_language": target}, str(tmp_path), _COVER_CONFIG)
    return captured


def test_tailor_system_prompt_is_byte_identical_across_every_hunt_language() -> None:
    systems = {lang: _capture_tailor_prompts(lang)["system"] for lang in _LANGUAGES}

    baseline = systems["en"]
    for lang, system in systems.items():
        assert system == baseline, f"system prompt diverged for output_language={lang!r} — breaks prompt caching"


def test_tailor_user_prompt_carries_the_language_signal_instead(tmp_path) -> None:
    en = _capture_tailor_prompts("en")
    de = _capture_tailor_prompts("de")

    assert "OUTPUT LANGUAGE" not in en["user"]
    assert "OUTPUT LANGUAGE — German" in de["user"]


def test_cover_system_prompt_is_byte_identical_across_every_hunt_language(tmp_path) -> None:
    systems = {lang: _capture_cover_prompts(lang, tmp_path)["system"] for lang in _LANGUAGES}

    baseline = systems["en"]
    for lang, system in systems.items():
        assert system == baseline, f"cover system prompt diverged for output_language={lang!r}"


def test_cover_user_prompt_carries_the_language_line_instead(tmp_path) -> None:
    en = _capture_cover_prompts("en", tmp_path)
    ja = _capture_cover_prompts("ja", tmp_path)

    assert "Write the letter in" not in en["system"]
    assert "Write the letter in Japanese." in ja["user"]
