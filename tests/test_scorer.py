"""Tests for pipeline/scorer.py — all LLM calls are mocked."""

import json
from unittest.mock import MagicMock, patch

import pytest

from job_hunter.pipeline import scorer

CONFIG = {
    "scoring": {
        "min_fit_score": 80,
        "max_years_experience_required": 4,
        "strategic_overrides": [
            {"company": "Infineon", "reason": "strategic", "min_score_override": 75},
        ],
    },
}

JOB = {
    "title": "Product Manager",
    "company": "TestCo",
    "url": "https://testco.com/job",
    "snippet": "PM role with agile, roadmapping, stakeholder management.",
}


# ── check_strategic_override ────────────────────────────────────────────────


def test_strategic_override_matches() -> None:
    result = scorer.check_strategic_override({"company": "Infineon Technologies"}, CONFIG)
    assert result == 75


def test_strategic_override_no_match() -> None:
    result = scorer.check_strategic_override({"company": "Unknown Corp"}, CONFIG)
    assert result is None


# ── score() ─────────────────────────────────────────────────────────────────


def test_score_valid_response(mock_llm_client) -> None:
    payload = json.dumps(
        {
            "score": 85,
            "matched_keywords": ["agile", "roadmap"],
            "gaps": ["automotive"],
            "years_exp_required": 3,
        }
    )
    with patch("job_hunter.pipeline.scorer.get_llm_client", return_value=mock_llm_client(payload)):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 85
    assert result["matched_keywords"] == ["agile", "roadmap"]
    assert result["gaps"] == ["automotive"]
    assert result["job"] is JOB


def test_score_requests_json_response_format(mock_llm_client) -> None:
    payload = json.dumps(
        {
            "score": 85,
            "matched_keywords": ["agile"],
            "gaps": [],
            "years_exp_required": 3,
        }
    )
    mock = mock_llm_client(payload)

    with patch("job_hunter.pipeline.scorer.get_llm_client", return_value=mock):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 85
    assert mock.complete.call_args.kwargs["response_format"] == "json"


def test_score_repairs_malformed_json_once() -> None:
    mock = MagicMock()
    mock.complete.side_effect = [
        MagicMock(content='{"score": 85, "matched_keywords": ["Git'),
        MagicMock(
            content=json.dumps(
                {
                    "score": 85,
                    "matched_keywords": ["Git"],
                    "gaps": [],
                    "years_exp_required": None,
                }
            )
        ),
    ]

    with patch("job_hunter.pipeline.scorer.get_llm_client", return_value=mock):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 85
    assert result["matched_keywords"] == ["Git"]
    assert mock.complete.call_count == 2
    assert "Convert this model response into valid JSON" in mock.complete.call_args.args[0].prompt


def test_score_json_parse_error(mock_llm_client) -> None:
    with patch("job_hunter.pipeline.scorer.get_llm_client", return_value=mock_llm_client("not json")):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 0
    assert "parse error" in result["gaps"]
    assert result["job"] is JOB


def test_score_api_error() -> None:
    mock = MagicMock()
    mock.complete.side_effect = Exception("API down")
    with patch("job_hunter.pipeline.scorer.get_llm_client", return_value=mock):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 0
    assert "api error" in result["gaps"]


# ── score_and_filter_jobs() ──────────────────────────────────────────────────


def test_build_scoring_resume_context_compacts_latex_noise() -> None:
    resume = r"""
% hidden draft bullet
\documentclass{article}
\usepackage{hyperref}
\begin{document}
\section{Summary}
Product manager with roadmapping and stakeholder leadership.
\textbf{Skills}: agile, discovery, analytics
\end{document}
"""
    config = {
        "scoring": {
            "prompt_context": {
                "resume_mode": "compact_text",
                "resume_max_chars": 200,
            }
        }
    }

    context = scorer.build_scoring_resume_context(resume, config)

    assert "hidden draft bullet" not in context
    assert "documentclass" not in context
    assert "Product manager with roadmapping" in context
    assert "agile, discovery, analytics" in context


def test_score_uses_configured_resume_and_jd_context_caps(monkeypatch) -> None:
    payload = json.dumps(
        {
            "score": 85,
            "matched_keywords": ["agile"],
            "gaps": [],
            "years_exp_required": 3,
        }
    )
    captured = {}

    def complete(req, **kwargs):
        captured["system"] = req.system or ""
        captured["user"] = req.prompt
        return MagicMock(content=payload)

    mock = MagicMock()
    mock.complete.side_effect = complete
    config = {
        "scoring": {
            "prompt_context": {
                "resume_mode": "compact_text",
                "resume_max_chars": 80,
                "job_description_max_chars": 12,
            }
        }
    }

    fake_resume = r"\documentclass{article}\begin{document}Roadmapping and agile leadership\end{document}"

    import builtins

    real_open = builtins.open

    def patched_open(path, *args, **kwargs):
        path_str = str(path)
        if path_str.endswith(".tex"):
            import io

            return io.StringIO(fake_resume)
        return real_open(path, *args, **kwargs)

    with (
        patch("job_hunter.pipeline.scorer.get_llm_client", return_value=mock),
        patch("builtins.open", side_effect=patched_open),
    ):
        result = scorer.score({**JOB, "snippet": "ABCDEFGHIJKLMNO"}, config)

    assert result["score"] == 85
    # Resume context is now in the system prompt (cached prefix); JD stays in user message.
    system = captured["system"]
    assert "Roadmapping and agile leadership" in system
    user = captured["user"]
    assert "ABCDEFGHIJKL" in user
    assert "MNO" not in user


def _score_result(score_val, years=3, company="TestCo"):
    job = {**JOB, "company": company}
    return {
        "score": score_val,
        "matched_keywords": [],
        "gaps": [],
        "years_exp_required": years,
        "job": job,
    }


@pytest.mark.parametrize(
    "score_kwargs, job_override, cfg, null_years, expected_count",
    [
        # score=85, standard job → passes threshold (80)
        ({"score_val": 85}, None, CONFIG, False, 1),
        # score=60, standard job → rejected below threshold
        ({"score_val": 60}, None, CONFIG, False, 0),
        # score=90 but 10 years required → rejected by years cap
        ({"score_val": 90, "years": 10}, None, CONFIG, False, 0),
        # score=78, Infineon → passes due to strategic override lowering threshold to 75
        ({"score_val": 78, "company": "Infineon"}, {"company": "Infineon"}, CONFIG, False, 1),
        # score=70, Infineon → still fails; 70 is below even the 75 override
        ({"score_val": 70, "company": "Infineon"}, {"company": "Infineon"}, CONFIG, False, 0),
        # score=90, years_exp_required=None → null years not rejected
        ({"score_val": 90}, None, CONFIG, True, 1),
    ],
)
def test_score_and_filter_jobs(score_kwargs, job_override, cfg, null_years, expected_count) -> None:
    job = {**JOB, **(job_override or {})}
    result = _score_result(**score_kwargs)
    if null_years:
        result["years_exp_required"] = None
    with patch.object(scorer, "score", return_value=result):
        matches = scorer.score_and_filter_jobs([job], config=cfg)
    assert len(matches) == expected_count


# ── bypass_max_years_experience ──────────────────────────────────────────────

_BYPASS_CONFIG = {
    "scoring": {
        "min_fit_score": 80,
        "max_years_experience_required": 4,
        "strategic_overrides": [
            {
                "company": "Infineon",
                "reason": "strategic",
                "min_score_override": 75,
                "bypass_max_years_experience": True,
            },
            {
                "company": "SAP",
                "reason": "strategic",
                "min_score_override": 75,
                "bypass_max_years_experience": False,
            },
        ],
    },
}


def test_strategic_override_companies_respects_bypass_flag() -> None:
    result = scorer.strategic_override_companies(_BYPASS_CONFIG)
    assert "Infineon" in result
    assert "SAP" not in result


def test_strategic_override_companies_excluded_when_key_absent() -> None:
    cfg = {"scoring": {"strategic_overrides": [{"company": "Bosch", "reason": "x", "min_score_override": 70}]}}
    assert scorer.strategic_override_companies(cfg) == []


@pytest.mark.parametrize(
    "company, expected_count",
    [
        # bypass_max_years_experience=True → high years ignored
        ("Infineon Technologies", 1),
        # bypass_max_years_experience=False → years cap still applied
        ("SAP SE", 0),
    ],
)
def test_filter_bypass_years_by_company(company, expected_count) -> None:
    job = {**JOB, "company": company}
    with patch.object(scorer, "score", return_value=_score_result(82, years=8, company=company)):
        matches = scorer.score_and_filter_jobs([job], config=_BYPASS_CONFIG)
    assert len(matches) == expected_count
