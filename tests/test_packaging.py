import tomllib
from pathlib import Path


def test_llm_sdks_ship_with_standard_install() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    optional = project["project"]["optional-dependencies"]

    assert "anthropic>=0.50.0" in dependencies
    assert "openai>=1.68.0" in dependencies
    assert "google-genai>=1.0.0" in dependencies
    assert "llm" not in optional
    assert optional["all"] == ["job-hunter-kit[browser,secrets]"]
