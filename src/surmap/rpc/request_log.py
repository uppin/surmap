"""Request-log ASGI middleware — product-blind.

`with_request_log(app)` wraps any ASGI app so every HTTP response leaves one log line:
method, path, status, duration and the response's `x-request-id`. A 5xx is an
`ERROR`, everything else `INFO`; a path in `quiet_paths` (a load-balancer probe) drops to
`DEBUG` unless it fails. A 5xx also logs the start of its response body — the reason a
route that handled its own failure gave the caller, which is otherwise only in the browser.
Bodies of any other status are never read. An exception escaping the app is logged with
its traceback and re-raised.

RPC dispatch has its own interceptor, so a plain ASGI route (sign-in, health, static
files) is otherwise invisible: a route answering 500 told the browser and nobody else.

The query string is never logged — a sign-in callback carries a one-time `code`.
Websocket scopes pass through untouched.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

__all__ = ["with_request_log"]

AsgiApp = Callable[..., Awaitable[None]]

_logger = logging.getLogger("surmap.rpc.http")
_REQUEST_ID_HEADER = b"x-request-id"
_SERVER_ERROR = 500
#: Most of a 5xx body that is logged — enough for a reason, not a page.
_MAX_BODY_CHARS = 300


def _request_id(message: dict[str, Any]) -> str:
    for name, value in message.get("headers", ()):
        if name.lower() == _REQUEST_ID_HEADER:
            return str(value.decode())
    return "-"


def _one_line_excerpt(body: bytes) -> str:
    """The start of `body` as a single bounded line, undecodable bytes replaced."""
    text = body[: _MAX_BODY_CHARS * 4].decode("utf-8", errors="replace")
    flat = " ".join(text.split())
    if len(flat) > _MAX_BODY_CHARS:
        return flat[:_MAX_BODY_CHARS] + "…"
    return flat


def with_request_log(app: AsgiApp, *, quiet_paths: frozenset[str] = frozenset()) -> AsgiApp:
    """Wrap `app` so each HTTP response is logged once, loudly when it is a 5xx."""

    async def wrapped(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        method = scope["method"]
        path = scope["path"]
        started = time.monotonic()
        status = 0
        request_id = "-"
        error_body = bytearray()

        async def logging_send(message: dict[str, Any]) -> None:
            nonlocal status, request_id
            if message["type"] == "http.response.start" and status == 0:
                status = message["status"]
                request_id = _request_id(message)
            elif message["type"] == "http.response.body" and status >= _SERVER_ERROR:
                if len(error_body) < _MAX_BODY_CHARS * 4:
                    error_body.extend(message.get("body", b""))
            await send(message)

        try:
            await app(scope, receive, logging_send)
        except Exception:
            _logger.exception(
                "%s %s failed after %.3fs request_id=%s",
                method,
                path,
                time.monotonic() - started,
                request_id,
            )
            raise

        if status >= _SERVER_ERROR:
            excerpt = _one_line_excerpt(bytes(error_body))
            _logger.error(
                "%s %s -> %d %.3fs request_id=%s%s",
                method,
                path,
                status,
                time.monotonic() - started,
                request_id,
                f" body={excerpt}" if excerpt else "",
            )
            return
        level = logging.DEBUG if path in quiet_paths else logging.INFO
        _logger.log(
            level,
            "%s %s -> %d %.3fs request_id=%s",
            method,
            path,
            status,
            time.monotonic() - started,
            request_id,
        )

    return wrapped
