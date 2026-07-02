"""Small localhost OTLP/HTTP JSON receiver for agent telemetry."""

from __future__ import annotations

import gzip
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
# Bumped by the request handler on any payload it cannot decode (protobuf/grpc clients,
# or anything not http/json) so doctor/telemetry-status can surface a protocol warning
# instead of failing silently the way a bare 200-with-accepted:0 response would.
LAST_REJECTED_CONTENT_TYPE = ""


def _decompress(body: bytes, content_encoding: str) -> bytes:
    if "gzip" in content_encoding.lower():
        try:
            return gzip.decompress(body)
        except OSError:
            return body
    return body


def handle_otlp_request(
    db_path: Path, body: bytes, *, content_type: str = "", content_encoding: str = ""
) -> tuple[int, int]:
    global LAST_REJECTED_CONTENT_TYPE
    if (
        content_type
        and "json" not in content_type.lower()
        and content_type.lower() not in ("", "application/octet-stream")
    ):
        LAST_REJECTED_CONTENT_TYPE = content_type
        return 200, 0
    try:
        payload = json.loads(_decompress(body, content_encoding))
        if not isinstance(payload, dict):
            return 200, 0
        return 200, ingest_otlp(db_path, payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        if content_type:
            LAST_REJECTED_CONTENT_TYPE = content_type
        return 200, 0


def _handler(db_path: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.server.last_activity = time.monotonic()  # type: ignore[attr-defined]
            if self.path == "/health":
                data = json.dumps(
                    {
                        "workspace": str(db_path.parent.parent.parent),
                        "last_rejected_content_type": LAST_REJECTED_CONTENT_TYPE,
                    }
                ).encode()
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
            body = self.rfile.read(length)
            if self.path.startswith("/v1/traces"):
                status, accepted = 200, 0  # accepted-but-ignored: no token data in traces
            else:
                status, accepted = handle_otlp_request(
                    db_path,
                    body,
                    content_type=self.headers.get("Content-Type", ""),
                    content_encoding=self.headers.get("Content-Encoding", ""),
                )
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


def collector_health(timeout: float = 0.3) -> dict[str, Any] | None:
    """Return the collector's /health payload, or None if it isn't reachable."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=timeout) as response:  # noqa: S310
            return dict(json.loads(response.read()))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _collector_workspace() -> str:
    health = collector_health()
    return str(health.get("workspace") or "") if health else ""


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
