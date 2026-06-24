from unittest.mock import MagicMock, patch

from job_hunter.pipeline import validator


def test_validate_accepts_fenced_json_with_preamble(mock_llm_client) -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "TestCo",
            "url": "https://example.com/jobs/pm",
            "snippet": "Open product manager role.",
        }
    ]
    api_cfg = {
        "llm": {
            "models": {"validation": "test-model"},
            "max_tokens": {"validation": 200},
            "max_workers": 1,
        },
        "http": {"url_verification": {"enabled": False}},
    }
    raw = 'Result:\n```json\n{"is_active": true, "over_experience": false, "reason": null}\n```'

    with patch("job_hunter.pipeline.validator.get_llm_client", return_value=mock_llm_client(raw)):
        valid, rejected = validator.validate(jobs, max_years=4, api_cfg=api_cfg)

    assert valid == jobs
    assert rejected == []


def test_validate_uses_injected_url_checker_before_llm() -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "TestCo",
            "url": "https://example.com/jobs/dead",
            "snippet": "Open product manager role.",
        }
    ]
    api_cfg = {
        "llm": {
            "models": {"validation": "test-model"},
            "max_tokens": {"validation": 200},
            "max_workers": 1,
        },
        "http": {"url_verification": {"enabled": True, "timeout_seconds": 5}},
    }

    def checker(url: str, timeout: int) -> bool:
        assert url == "https://example.com/jobs/dead"
        assert timeout == 5
        return False

    with patch("job_hunter.pipeline.validator.get_llm_client") as client:
        valid, rejected = validator.validate(
            jobs,
            max_years=4,
            api_cfg=api_cfg,
            url_checker=checker,
        )

    assert valid == []
    assert rejected[0]["_rejection_reason"] == "dead_url"
    client.assert_not_called()


def test_validate_rejects_explicitly_closed_snippet_without_llm() -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "ClosedCo",
            "url": "https://example.com/jobs/closed",
            "snippet": "This job has expired and is no longer available.",
        }
    ]
    api_cfg = {
        "llm": {
            "models": {"validation": "test-model"},
            "max_tokens": {"validation": 200},
            "max_workers": 1,
        },
        "http": {"url_verification": {"enabled": False}},
    }

    with patch("job_hunter.pipeline.validator.get_llm_client") as client:
        valid, rejected = validator.validate(jobs, max_years=4, api_cfg=api_cfg)

    assert valid == []
    assert "no longer available" in rejected[0]["_rejection_reason"]
    client.assert_not_called()


def test_validate_rejects_explicit_over_experience_without_llm() -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "SeniorCo",
            "url": "https://example.com/jobs/senior",
            "snippet": "Requirements: at least 8 years of product management experience required.",
        }
    ]
    api_cfg = {
        "llm": {
            "models": {"validation": "test-model"},
            "max_tokens": {"validation": 200},
            "max_workers": 1,
        },
        "http": {"url_verification": {"enabled": False}},
    }

    with patch("job_hunter.pipeline.validator.get_llm_client") as client:
        valid, rejected = validator.validate(jobs, max_years=4, api_cfg=api_cfg)

    assert valid == []
    assert rejected[0]["_rejection_reason"] == "requires 8+ years experience"
    client.assert_not_called()


def test_validate_sends_ambiguous_experience_to_llm(mock_llm_client) -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "AmbiguousCo",
            "url": "https://example.com/jobs/pm",
            "snippet": "You will partner with experienced teams across 8 product lines.",
        }
    ]
    api_cfg = {
        "llm": {
            "models": {"validation": "test-model"},
            "max_tokens": {"validation": 200},
            "max_workers": 1,
        },
        "http": {"url_verification": {"enabled": False}},
    }
    raw = '{"is_active": true, "over_experience": false, "reason": null}'

    with patch("job_hunter.pipeline.validator.get_llm_client", return_value=mock_llm_client(raw)) as client:
        valid, rejected = validator.validate(jobs, max_years=4, api_cfg=api_cfg)

    assert valid == jobs
    assert rejected == []
    client.assert_called()


def test_validate_requests_json_response_format(mock_llm_client) -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "JsonCo",
            "url": "https://example.com/jobs/pm",
            "snippet": "Open product manager role.",
        }
    ]
    api_cfg = {
        "llm": {
            "models": {"validation": "test-model"},
            "max_tokens": {"validation": 200},
            "max_workers": 1,
        },
        "http": {"url_verification": {"enabled": False}},
    }
    mock = mock_llm_client('{"is_active": true, "over_experience": false, "reason": null}')

    with patch("job_hunter.pipeline.validator.get_llm_client", return_value=mock):
        valid, rejected = validator.validate(jobs, max_years=4, api_cfg=api_cfg)

    assert valid == jobs
    assert rejected == []
    assert mock.complete.call_args.kwargs["response_format"] == "json"


def test_validate_strategic_company_bypasses_deterministic_years_rejection(mock_llm_client) -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "Infineon Technologies",
            "url": "https://example.com/jobs/infineon",
            "snippet": "Requirements: at least 8 years of product management experience required.",
        }
    ]
    api_cfg = {
        "llm": {
            "models": {"validation": "test-model"},
            "max_tokens": {"validation": 200},
            "max_workers": 1,
        },
        "http": {"url_verification": {"enabled": False}},
    }
    raw = '{"is_active": true, "over_experience": false, "reason": null}'

    with patch("job_hunter.pipeline.validator.get_llm_client", return_value=mock_llm_client(raw)):
        valid, rejected = validator.validate(
            jobs,
            max_years=4,
            api_cfg=api_cfg,
            max_years_bypass_companies=["Infineon"],
        )

    assert valid == jobs
    assert rejected == []


def test_validate_repairs_malformed_json_once() -> None:
    jobs = [
        {
            "title": "Product Manager",
            "company": "RepairCo",
            "url": "https://example.com/jobs/pm",
            "snippet": "Open product manager role.",
        }
    ]
    api_cfg = {
        "llm": {
            "models": {"validation": "test-model"},
            "max_tokens": {"validation": 200},
            "max_workers": 1,
        },
        "http": {"url_verification": {"enabled": False}},
    }
    mock = MagicMock()
    mock.complete.side_effect = [
        MagicMock(content='{"is_active": tru'),
        MagicMock(content='{"is_active": true, "over_experience": false, "reason": null}'),
    ]

    with patch("job_hunter.pipeline.validator.get_llm_client", return_value=mock):
        valid, rejected = validator.validate(jobs, max_years=4, api_cfg=api_cfg)

    assert valid == jobs
    assert rejected == []
    assert mock.complete.call_count == 2
    assert "Convert this model response into valid JSON" in mock.complete.call_args.args[0].prompt
