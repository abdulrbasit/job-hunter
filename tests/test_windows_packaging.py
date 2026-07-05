from pathlib import Path


def test_windows_pyinstaller_spike_is_isolated_and_keeps_console_enabled() -> None:
    root = Path(__file__).parents[1]
    spec = (root / "packaging" / "windows" / "job-hunter.spec").read_text(encoding="utf-8")

    assert 'name="job-hunter"' in spec
    assert "console=True" in spec
    assert "dashboard.html" in spec
    assert "job_hunter/templates" in spec
    assert 'collect_submodules("anthropic", filter=runtime_module)' in spec
    assert 'collect_submodules("openai", filter=runtime_module)' in spec
    assert 'collect_submodules("google.genai", filter=runtime_module)' in spec
    assert "playwright" not in spec.lower()


def test_windows_packaging_docs_state_external_runtime_expectations() -> None:
    root = Path(__file__).parents[1]
    docs = (root / "docs" / "windows-packaging.md").read_text(encoding="utf-8")

    assert "WebView2 Evergreen" in docs
    assert "Playwright Chromium is intentionally not bundled" in docs
    assert "onedir" in docs
