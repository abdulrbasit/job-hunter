from pathlib import Path

import tomllib


def test_llm_sdks_are_optional() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    optional = project["project"]["optional-dependencies"]

    assert not any(
        name in dependency
        for name in ("anthropic", "openai", "google-genai")
        for dependency in dependencies
    )
    assert optional["llm"] == [
        "anthropic>=0.50.0",
        "openai>=1.68.0",
        "google-genai>=1.0.0",
    ]
    assert "job-hunter-kit[llm,browser,secrets]" in optional["all"]
