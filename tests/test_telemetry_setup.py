from __future__ import annotations

import json
from pathlib import Path

from job_hunter.metrics.setup import configure_codex_telemetry, install_workspace_telemetry


def test_workspace_telemetry_setup_is_idempotent(tmp_path: Path) -> None:
    install_workspace_telemetry(tmp_path)
    first_claude = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    first_codex = (tmp_path / ".codex" / "hooks.json").read_text(encoding="utf-8")

    install_workspace_telemetry(tmp_path)

    assert (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8") == first_claude
    assert (tmp_path / ".codex" / "hooks.json").read_text(encoding="utf-8") == first_codex
    assert json.loads(first_claude)["env"]["OTEL_LOG_USER_PROMPTS"] == "0"


def test_codex_global_config_appends_once_and_preserves_existing_text(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('model = "gpt-5.4"\n', encoding="utf-8")

    assert configure_codex_telemetry(config) == "configured"
    first = config.read_text(encoding="utf-8")
    assert configure_codex_telemetry(config) == "already-configured"
    assert config.read_text(encoding="utf-8") == first
    assert 'model = "gpt-5.4"' in first
    assert "[otel]" in first
    assert "127.0.0.1:4318" in first


def test_codex_global_config_preserves_unrelated_otel(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    original = '[otel]\nexporter = { otlp-http = { endpoint = "https://otel.example/v1/logs" } }\n'
    config.write_text(original, encoding="utf-8")

    assert configure_codex_telemetry(config) == "conflict"
    assert config.read_text(encoding="utf-8") == original
