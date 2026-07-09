from pathlib import Path


def test_linux_pyinstaller_spike_is_isolated_and_windowed() -> None:
    root = Path(__file__).parents[1]
    spec = (root / "packaging" / "linux" / "job-hunter.spec").read_text(encoding="utf-8")

    assert 'name="job-hunter"' in spec
    assert "console=False" in spec
    assert "dashboard.html" in spec
    assert "dashboard.css" in spec
    assert "dashboard.js" in spec
    assert "countries.json" in spec
    assert "filters.json" in spec
    assert "companies.json" in spec
    assert "job_hunter/templates" in spec
    assert 'collect_submodules("anthropic", filter=runtime_module)' in spec
    assert 'collect_submodules("openai", filter=runtime_module)' in spec
    assert 'collect_submodules("google.genai", filter=runtime_module)' in spec
    assert "playwright" not in spec.lower()


def test_linux_desktop_file_points_at_dash_command() -> None:
    root = Path(__file__).parents[1]
    desktop = (root / "packaging" / "linux" / "job-hunter.desktop").read_text(encoding="utf-8")

    assert "Type=Application" in desktop
    assert "Exec=job-hunter dash" in desktop
    assert "Terminal=false" in desktop


def test_linux_packaging_docs_state_unbuilt_status_and_appimage_gap() -> None:
    root = Path(__file__).parents[1]
    docs = (root / "docs" / "linux-packaging.md").read_text(encoding="utf-8")

    assert "unbuilt" in docs.lower()
    assert "appimagetool" in docs.lower()
    assert "GPG" in docs
    assert "do not** publish, bump the version, or trigger a" in docs
