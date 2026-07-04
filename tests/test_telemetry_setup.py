from __future__ import annotations

import json
from pathlib import Path

from job_hunter.metrics.setup import (
    configure_codex_telemetry,
    install_global_telemetry_env,
    install_workspace_telemetry,
)


def test_workspace_telemetry_setup_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    install_workspace_telemetry(workspace, home=home)
    first_claude = (workspace / ".claude" / "settings.json").read_text(encoding="utf-8")
    first_codex = (workspace / ".codex" / "hooks.json").read_text(encoding="utf-8")

    install_workspace_telemetry(workspace, home=home)

    assert (workspace / ".claude" / "settings.json").read_text(encoding="utf-8") == first_claude
    assert (workspace / ".codex" / "hooks.json").read_text(encoding="utf-8") == first_codex
    env = json.loads(first_claude)["env"]
    assert env["OTEL_LOG_USER_PROMPTS"] == "0"
    assert env["OTEL_METRICS_EXPORTER"] == "otlp"


def test_workspace_telemetry_setup_also_writes_global_settings(tmp_path: Path) -> None:
    """Desktop app's own OTel exporter may not honor project-scoped env — merge into
    the user's global settings too, since that's documented as shared everywhere."""
    home = tmp_path / "home"
    install_workspace_telemetry(tmp_path / "workspace", home=home)

    global_env = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))["env"]
    assert global_env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    assert global_env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:4318"


def test_install_global_telemetry_env_never_clobbers_unrelated_keys(tmp_path: Path) -> None:
    global_path = tmp_path / ".claude" / "settings.json"
    global_path.parent.mkdir(parents=True)
    global_path.write_text(json.dumps({"env": {"SOME_OTHER_VAR": "keep-me"}, "model": "opus"}), encoding="utf-8")

    install_global_telemetry_env(tmp_path)

    settings = json.loads(global_path.read_text(encoding="utf-8"))
    assert settings["model"] == "opus"
    assert settings["env"]["SOME_OTHER_VAR"] == "keep-me"
    assert settings["env"]["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"


def test_install_global_telemetry_env_is_idempotent(tmp_path: Path) -> None:
    install_global_telemetry_env(tmp_path)
    first = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")

    install_global_telemetry_env(tmp_path)

    assert (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8") == first


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
