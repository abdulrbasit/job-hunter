"""Assembles the three dashboard source files (shell/css/js) into one HTML string.

pywebview's create_window(html=...) takes one in-memory string with no base URL,
so relative <link href="dashboard.css"> / <script src="dashboard.js"> in the shell
can't resolve at runtime. Source stays split into three files for maintainability;
this inlines them back together only at launch time.
"""

from __future__ import annotations

_CSS_LINK_TAG = '<link rel="stylesheet" href="dashboard.css">'
_JS_SRC_TAG = '<script src="dashboard.js"></script>'


def build_dashboard_html(shell: str, css: str, js: str) -> str:
    if _CSS_LINK_TAG not in shell:
        raise ValueError(f"dashboard.html shell is missing {_CSS_LINK_TAG!r}")
    if _JS_SRC_TAG not in shell:
        raise ValueError(f"dashboard.html shell is missing {_JS_SRC_TAG!r}")
    html = shell.replace(_CSS_LINK_TAG, f"<style>\n{css}</style>")
    html = html.replace(_JS_SRC_TAG, f"<script>\n{js}</script>")
    return html
