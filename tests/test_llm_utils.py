from job_hunter.core.llm_utils import extract_json_object


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
