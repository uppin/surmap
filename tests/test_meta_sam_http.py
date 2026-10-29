"""Urllib transport for the Meta SAM adapter, against a local socket.

These tests do not call api.meta.ai. They check that the default
transport POSTs JSON and that an HTTP error does not echo the key.
"""

from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from surmap.survey.meta_sam import (
    DEFAULT_MODEL,
    MetaSamDetector,
    MetaSamError,
    UrllibMetaTransport,
)
from surmap.survey.sam import RawFrame

FIXTURE_KEY = "fixture-key"


def a_jpeg_frame() -> RawFrame:
    image = Image.new("RGB", (8, 8), (20, 40, 60))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return RawFrame(7, 700, 0, 8, 8, "mjpeg", buffer.getvalue())


def a_response(text: str) -> dict[str, object]:
    usage: dict[str, object] = {"input_tokens": 11, "output_tokens": 22}
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": usage,
    }


class _CapturedRequest(BaseHTTPRequestHandler):
    body: bytes = b""
    authorization: str | None = None
    status_code: int = 200
    response_body: bytes = b""

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        type(self).body = self.rfile.read(length)
        type(self).authorization = self.headers.get("Authorization")
        payload = type(self).response_body
        self.send_response(type(self).status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def _serve(status_code: int, response_body: bytes) -> tuple[ThreadingHTTPServer, int]:
    _CapturedRequest.status_code = status_code
    _CapturedRequest.response_body = response_body
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CapturedRequest)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    assert isinstance(port, int)
    return server, port


async def test_the_urllib_transport_posts_json_to_the_endpoint() -> None:
    # Given a local stand-in for the Responses endpoint
    server, port = _serve(200, json.dumps(a_response("")).encode())
    try:
        detector = MetaSamDetector(
            api_key=FIXTURE_KEY,
            endpoint=f"http://127.0.0.1:{port}/v1/responses",
            transport=UrllibMetaTransport(),
        )

        # When a frame is segmented
        detections = await detector.detect(a_jpeg_frame())
    finally:
        server.shutdown()

    # Then the process POSTed the bearer token and a JSON body, and got no matches
    posted = json.loads(_CapturedRequest.body)
    assert isinstance(posted, dict)
    assert _CapturedRequest.authorization == f"Bearer {FIXTURE_KEY}"
    assert posted["model"] == DEFAULT_MODEL
    assert detections == ()


async def test_an_http_error_does_not_include_the_key() -> None:
    # Given the endpoint rejects the call
    server, port = _serve(401, b'{"error":{"message":"nope"}}')
    try:
        detector = MetaSamDetector(
            api_key=FIXTURE_KEY,
            endpoint=f"http://127.0.0.1:{port}/v1/responses",
            transport=UrllibMetaTransport(),
        )

        # When a frame is segmented
        with pytest.raises(MetaSamError, match="401") as raised:
            await detector.detect(a_jpeg_frame())
    finally:
        server.shutdown()

    # Then the failure names the status and not the bearer token
    assert FIXTURE_KEY not in str(raised.value)
