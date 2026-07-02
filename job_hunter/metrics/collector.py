"""Small localhost OTLP/HTTP JSON receiver for agent telemetry."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from job_hunter.metrics.telemetry import ingest_otlp

HOST = "127.0.0.1"
PORT = 4318
IDLE_TIMEOUT_SECONDS = 15 * 60


def handle_otlp_request(db_path: Path, body: bytes) -> tuple[int, int]:
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            return 200, 0
        return 200, ingest_otlp(db_path, payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        return 200, 0


def _handler(db_path: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.server.last_activity = time.monotonic()  # type: ignore[attr-defined]
            if self.path == "/health":
                data = json.dumps({"workspace": str(db_path.parent.parent.parent)}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            self.server.last_activity = time.monotonic()  # type: ignore[attr-defined]
            length = int(self.headers.get("Content-Length", "0") or 0)
            status, accepted = handle_otlp_request(db_path, self.rfile.read(length))
            data = json.dumps({"accepted": accepted}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    return Handler


def serve(workspace: Path) -> None:
    db_path = workspace.resolve() / "outputs" / "state" / "metrics.db"
    server = ThreadingHTTPServer((HOST, PORT), _handler(db_path))
    server.last_activity = time.monotonic()  # type: ignore[attr-defined]

    def watchdog() -> None:
        while True:
            time.sleep(30)
            if time.monotonic() - server.last_activity > IDLE_TIMEOUT_SECONDS:  # type: ignore[attr-defined]
                server.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    server.serve_forever()


def _collector_workspace() -> str:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=0.3) as response:  # noqa: S310
            return str(json.loads(response.read()).get("workspace") or "")
    except (OSError, ValueError, json.JSONDecodeError):
        return ""


def ensure_collector(workspace: Path) -> bool:
    active_workspace = _collector_workspace()
    if active_workspace:
        return Path(active_workspace).resolve() == workspace.resolve()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(workspace),
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(  # noqa: S603 - fixed interpreter/module; workspace is one argument
            [sys.executable, "-m", "job_hunter.metrics.collector", "--workspace", str(workspace)],
            **kwargs,
        )
        return True
    except OSError:
        return False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    serve(args.workspace)


if __name__ == "__main__":
    main()
