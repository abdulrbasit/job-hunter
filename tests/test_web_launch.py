from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


def test_dashboard_launches_maximized(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    def create_window(*args, **kwargs):
        captured.update(kwargs)
        return object()

    fake_webview = SimpleNamespace(create_window=create_window, start=lambda **_kwargs: None)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    from job_hunter.ux.web import launch

    launch(tmp_path)

    assert captured["maximized"] is True
    assert captured["width"] == 1200
    assert captured["height"] == 800
    assert captured["min_size"] == (900, 600)
    assert 'href="dashboard.css"' not in captured["html"]
    assert 'src="dashboard.js"' not in captured["html"]
    assert "<style>" in captured["html"]
