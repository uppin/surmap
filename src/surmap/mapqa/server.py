"""Local ``POST /ask`` for the web viewer.

The viewer sends ``{"question", "snapshot_path"?}`` and reads
``{"answer", "landmark_ids", "highlight_points"}``. ``snapshot_path`` is a
local file. The process is meant to run on the responder's machine.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from surmap.mapqa.errors import (
    EmptyModelOutput,
    InvalidMapAnswer,
    MapQaError,
    ModelApiError,
    ModelApiKeyMissing,
    SnapshotError,
    WonderFullRefused,
)
from surmap.mapqa.qa import MapQa

_MAX_BODY = 1_000_000


@dataclass
class RunningMapQaServer:
    """A server started in a background thread. ``close`` stops it."""

    httpd: ThreadingHTTPServer
    thread: threading.Thread

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        shown = host.decode() if isinstance(host, bytes) else host
        return f"http://{shown}:{port}"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def __enter__(self) -> RunningMapQaServer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def start_mapqa_server(qa: MapQa, *, host: str = "127.0.0.1", port: int = 0) -> RunningMapQaServer:
    """Bind ``host:port`` (port 0 picks a free port) and serve until ``close``."""
    httpd = ThreadingHTTPServer((host, port), _handler(qa))
    thread = threading.Thread(target=httpd.serve_forever, name="mapqa-http", daemon=True)
    thread.start()
    return RunningMapQaServer(httpd, thread)


def serve_mapqa(qa: MapQa, *, host: str, port: int) -> None:
    """Serve until the process is interrupted."""
    running = start_mapqa_server(qa, host=host, port=port)
    try:
        print(f"Ask the map listening on {running.url}/ask", flush=True)
        running.thread.join()
    finally:
        running.close()


def ask_response(qa: MapQa, body: dict[str, object]) -> tuple[int, dict[str, object]]:
    """The ``POST /ask`` contract, without the socket."""
    question = body.get("question")
    if not isinstance(question, str) or not question.strip():
        return 400, {"error": "question is required"}
    target, failure = _snapshot_for_request(qa, body)
    if failure is not None:
        return failure
    if target is None:
        return 500, {"error": "snapshot was not loaded"}
    try:
        answer = target.ask(question)
    except WonderFullRefused as exc:
        return 400, {"error": str(exc)}
    except ModelApiKeyMissing as exc:
        return 400, {"error": str(exc)}
    except (InvalidMapAnswer, EmptyModelOutput, ModelApiError, SnapshotError) as exc:
        return 502, {"error": str(exc)}
    except MapQaError as exc:
        return 502, {"error": str(exc)}
    return 200, answer.as_dict()


def _snapshot_for_request(
    qa: MapQa, body: dict[str, object]
) -> tuple[MapQa | None, tuple[int, dict[str, object]] | None]:
    if "snapshot_path" not in body or body.get("snapshot_path") is None:
        return qa, None
    snapshot_path = body.get("snapshot_path")
    if not isinstance(snapshot_path, str) or not snapshot_path.strip():
        return None, (400, {"error": "snapshot_path must be a file path"})
    path = Path(snapshot_path)
    if not path.is_file():
        return None, (404, {"error": f"snapshot not found: {snapshot_path}"})
    try:
        return qa.with_snapshot(path), None
    except SnapshotError as exc:
        return None, (400, {"error": str(exc)})


def _handler(qa: MapQa) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/ask":
                _send(self, 404, {"error": "not found"})
                return
            status, payload = ask_response(qa, _read_json(self))
            _send(self, status, payload)

        def do_OPTIONS(self) -> None:
            if urlsplit(self.path).path != "/ask":
                _send(self, 404, {"error": "not found"})
                return
            self.send_response(204)
            _cors(self)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    length_header = handler.headers.get("Content-Length")
    if length_header is None:
        return {}
    try:
        length = int(length_header)
    except ValueError:
        return {}
    if length < 0 or length > _MAX_BODY:
        return {}
    raw = handler.rfile.read(length)
    try:
        parsed: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): value for key, value in parsed.items()}


def _send(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    _cors(handler)
    handler.end_headers()
    handler.wfile.write(body)


def _cors(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
