"""Install non-invasive Claude Code and Codex telemetry configuration."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

_ENDPOINT = "http://127.0.0.1:4318"


def _hook(backend: str, event: str) -> dict[str, object]:
    return {
        "hooks": [
            {
                "type": "command",
                "command": f"job-hunter internal telemetry-hook --backend {backend} --event {event}",
                "timeout": 10,
            }
        ]
    }


def _merge_hooks(existing: dict, additions: dict[str, list[dict]]) -> dict:
    hooks = existing.setdefault("hooks", {})
    for event, entries in additions.items():
        current = hooks.setdefault(event, [])
        commands = {
            hook.get("command") for group in current for hook in group.get("hooks", []) if isinstance(group, dict)
        }
        for entry in entries:
            command = entry["hooks"][0]["command"]
            if command not in commands:
                current.append(entry)
    return existing


def install_workspace_telemetry(workspace: Path) -> None:
    claude_path = workspace / ".claude" / "settings.json"
    codex_path = workspace / ".codex" / "hooks.json"
    claude_path.parent.mkdir(parents=True, exist_ok=True)
    codex_path.parent.mkdir(parents=True, exist_ok=True)

    claude = json.loads(claude_path.read_text(encoding="utf-8")) if claude_path.exists() else {}
    claude.setdefault("env", {}).update(
        {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_METRICS_EXPORTER": "none",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_ENDPOINT": _ENDPOINT,
            "OTEL_LOG_USER_PROMPTS": "0",
            "OTEL_LOG_TOOL_DETAILS": "0",
        }
    )
    _merge_hooks(
        claude,
        {
            "UserPromptSubmit": [_hook("claude-code", "prompt")],
            "Stop": [_hook("claude-code", "stop")],
            "SessionEnd": [_hook("claude-code", "session-end")],
        },
    )
    claude_path.write_text(json.dumps(claude, indent=2) + "\n", encoding="utf-8")

    codex = json.loads(codex_path.read_text(encoding="utf-8")) if codex_path.exists() else {}
    _merge_hooks(
        codex,
        {
            "UserPromptSubmit": [_hook("codex", "prompt")],
            "Stop": [_hook("codex", "stop")],
        },
    )
    codex_path.write_text(json.dumps(codex, indent=2) + "\n", encoding="utf-8")


def configure_codex_telemetry(config_path: Path) -> str:
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        try:
            parsed = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return "invalid"
        if "otel" in parsed:
            endpoint = json.dumps(parsed["otel"])
            return "already-configured" if "127.0.0.1:4318" in endpoint else "conflict"
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        text = ""
    separator = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    block = (
        "[otel]\n"
        'environment = "job-hunter"\n'
        "log_user_prompt = false\n"
        'exporter = { otlp-http = { endpoint = "http://127.0.0.1:4318/v1/logs", protocol = "json" } }\n'
    )
    config_path.write_text(text + separator + block, encoding="utf-8")
    return "configured"
