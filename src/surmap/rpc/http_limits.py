"""Request size limits for kit HTTP listeners."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

__all__ = [
    "ClientDisconnected",
    "MAX_REQUEST_BODY_BYTES",
    "RequestBodyTooLargeError",
    "read_limited_body",
]

MAX_REQUEST_BODY_BYTES = 4 * 1024 * 1024


class RequestBodyTooLargeError(Exception):
    """The request body exceeded the configured limit."""


class ClientDisconnected(Exception):
    """The client closed the connection before the request finished."""


async def read_limited_body(
    receive: Callable[[], Awaitable[dict[str, Any]]],
    *,
    max_bytes: int = MAX_REQUEST_BODY_BYTES,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        message_type = message["type"]
        if message_type == "http.disconnect":
            raise ClientDisconnected
        if message_type != "http.request":
            continue
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > max_bytes:
            raise RequestBodyTooLargeError
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)
