"""`with_request_log` — one log line per HTTP response, loud when the server failed.

The middleware wraps any ASGI app. The RPC interceptor logs RPC dispatch only, so a plain ASGI
route (sign-in, health, static files) that answers 500 left no trace; this wrapper is the
product-blind record of what the edge answered. Query strings are never logged: a sign-in
callback carries a one-time `code`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import pytest

from surmap.rpc.request_log import with_request_log

LOGGER = "surmap.rpc.http"


def _http_scope(path: str = "/x", *, query: bytes = b"", method: str = "GET") -> dict[str, Any]:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query,
        "headers": [(b"x-request-id", b"req-inbound")],
    }


def _responder(
    status: int,
    headers: Sequence[tuple[bytes, bytes]] = (),
    body_chunks: Sequence[bytes] = (b"body",),
) -> Any:
    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": status, "headers": list(headers)})
        for index, chunk in enumerate(body_chunks):
            more = index < len(body_chunks) - 1
            await send({"type": "http.response.body", "body": chunk, "more_body": more})

    return app


async def _drive(app: Any, scope: dict[str, Any]) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    await app(scope, receive, send)
    return sent


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == LOGGER]


async def test_a_server_error_is_logged_at_error_with_method_path_status_and_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    app = with_request_log(_responder(500, [(b"x-request-id", b"req-from-edge")]))

    await _drive(app, _http_scope("/_api/auth/start"))

    (record,) = _records(caplog)
    assert record.levelno == logging.ERROR
    message = record.getMessage()
    assert "GET" in message
    assert "/_api/auth/start" in message
    assert "500" in message
    assert "req-from-edge" in message


async def test_a_client_error_is_logged_at_info(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    await _drive(with_request_log(_responder(404)), _http_scope("/missing"))

    (record,) = _records(caplog)
    assert record.levelno == logging.INFO
    assert "404" in record.getMessage()


async def test_a_success_is_logged_at_info(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    await _drive(with_request_log(_responder(200)), _http_scope("/index.html"))

    (record,) = _records(caplog)
    assert record.levelno == logging.INFO


async def test_a_quiet_path_is_logged_at_debug_so_a_probe_does_not_flood_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    app = with_request_log(_responder(200), quiet_paths=frozenset({"/health/is_alive"}))

    await _drive(app, _http_scope("/health/is_alive"))

    (record,) = _records(caplog)
    assert record.levelno == logging.DEBUG


async def test_a_failing_quiet_path_is_still_logged_at_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    app = with_request_log(_responder(503), quiet_paths=frozenset({"/health/is_alive"}))

    await _drive(app, _http_scope("/health/is_alive"))

    (record,) = _records(caplog)
    assert record.levelno == logging.ERROR


async def test_the_query_string_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    scope = _http_scope("/_api/auth/callback", query=b"code=one-time-secret&state=abc")

    await _drive(with_request_log(_responder(302)), scope)

    (record,) = _records(caplog)
    assert "one-time-secret" not in record.getMessage()
    assert "code=" not in record.getMessage()


async def test_a_server_error_logs_what_the_response_said_so_the_cause_is_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    app = with_request_log(_responder(500, body_chunks=[b"SURMAP_", b"SURVEY_API_TOKEN"]))

    await _drive(app, _http_scope("/_api/auth/start"))

    (record,) = _records(caplog)
    assert "SURMAP_SURVEY_API_TOKEN" in record.getMessage()


async def test_a_long_server_error_body_is_cut_and_stays_on_one_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    body = b"first line\n" + b"x" * 5000

    await _drive(with_request_log(_responder(500, body_chunks=[body])), _http_scope())

    (record,) = _records(caplog)
    message = record.getMessage()
    assert "first line" in message
    assert "\n" not in message
    assert len(message) < 1000


async def test_only_a_server_error_body_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    await _drive(with_request_log(_responder(404, body_chunks=[b"private-ish"])), _http_scope())
    await _drive(with_request_log(_responder(200, body_chunks=[b"page-content"])), _http_scope())

    messages = [record.getMessage() for record in _records(caplog)]
    assert len(messages) == 2
    assert all("private-ish" not in m and "page-content" not in m for m in messages)


async def test_the_response_passes_through_unchanged() -> None:
    inner_headers = [(b"content-type", b"text/plain")]

    sent = await _drive(with_request_log(_responder(500, inner_headers)), _http_scope())

    assert sent == [
        {"type": "http.response.start", "status": 500, "headers": inner_headers},
        {"type": "http.response.body", "body": b"body", "more_body": False},
    ]


async def test_an_exception_from_the_app_is_logged_with_its_traceback_and_re_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    async def failing(scope: dict[str, Any], receive: Any, send: Any) -> None:
        raise RuntimeError("route blew up")

    with pytest.raises(RuntimeError, match="route blew up"):
        await _drive(with_request_log(failing), _http_scope("/boom"))

    (record,) = _records(caplog)
    assert record.levelno == logging.ERROR
    assert "/boom" in record.getMessage()
    assert record.exc_info is not None


async def test_a_websocket_scope_passes_through_without_a_log_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    seen: list[str] = []

    async def ws_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    await _drive(with_request_log(ws_app), {"type": "websocket", "path": "/_workers/connect"})

    assert seen == ["websocket"]
    assert _records(caplog) == []
