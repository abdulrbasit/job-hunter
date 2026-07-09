"""pywebview-based interactive dashboard launcher."""

from __future__ import annotations

from pathlib import Path


def launch(root: Path) -> None:
    """Open the Job Hunter dashboard in a native OS window."""
    import importlib.resources
    import secrets

    import webview

    from job_hunter.ux.web.api import DashAPI
    from job_hunter.ux.web.assembly import build_dashboard_html

    api = DashAPI(root)
    web_dir = importlib.resources.files("job_hunter.ux.web")
    shell = web_dir.joinpath("dashboard.html").read_text(encoding="utf-8")
    css = web_dir.joinpath("dashboard.css").read_text(encoding="utf-8")
    js = web_dir.joinpath("dashboard.js").read_text(encoding="utf-8")
    nonce = secrets.token_urlsafe(16)
    html_content = build_dashboard_html(shell, css, js, nonce)

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
