import pytest

from job_hunter.core.llm_utils import extract_json_object, get_llm_role_settings


def test_extract_json_object_strips_fence_and_preamble() -> None:
    raw = 'Here is the result:\n```json\n{"ok": true}\n```\nThanks'

    assert extract_json_object(raw) == '{"ok": true}'


def test_extract_json_object_ignores_trailing_json_like_text() -> None:
    raw = '{"title": "Product Manager"}\n{"debug": "ignored"}'

    assert extract_json_object(raw) == '{"title": "Product Manager"}'


def test_extract_json_object_accepts_array_payload() -> None:
    raw = 'Result:\n[{"title": "Product Owner"}]\nDone'

    assert extract_json_object(raw) == '[{"title": "Product Owner"}]'


def test_extract_json_object_returns_original_when_no_object() -> None:
    assert extract_json_object("not json") == "not json"


def test_get_llm_role_settings_uses_config_values() -> None:
    settings = get_llm_role_settings(
        "validation",
        api_cfg={
            "llm": {
                "models": {"validation": "configured-model"},
                "max_tokens": {"validation": 123},
            }
        },
    )

    assert settings.model == "configured-model"
    assert settings.max_tokens == 123


def test_get_llm_role_settings_requires_explicit_role_keys() -> None:
    with pytest.raises(KeyError, match="llm.models.jd_extraction"):
        get_llm_role_settings(
            "jd_extraction",
            api_cfg={"llm": {"models": {}, "max_tokens": {}}},
        )


def test_get_llm_role_settings_uses_default_provider_without_default_model() -> None:
    settings = get_llm_role_settings(
        "scoring",
        api_cfg={
            "llm": {
                "default_provider": "ollama",
                "models": {"scoring": "local-model"},
                "max_tokens": {"scoring": 999},
            }
        },
    )

    assert settings.provider == "ollama"
    assert settings.model == "local-model"
