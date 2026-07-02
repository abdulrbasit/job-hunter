"""pywebview-based interactive dashboard launcher."""

from __future__ import annotations

from pathlib import Path


def launch(root: Path) -> None:
    """Open the Job Hunter dashboard in a native OS window."""
    import importlib.resources

    import webview

    from job_hunter.ux.web.api import DashAPI

    api = DashAPI(root)
    html_path = importlib.resources.files("job_hunter.ux.web").joinpath("dashboard.html")
    html_content = html_path.read_text(encoding="utf-8")

    window = webview.create_window(
        "Job Hunter",
        html=html_content,
        js_api=api,
        width=1200,
        height=800,
        min_size=(900, 600),
        maximized=True,
    )
    webview.start(debug=False)
    _ = window
