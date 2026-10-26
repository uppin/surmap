"""Bounded HTTP body reads for kit listeners."""

from __future__ import annotations

import pytest

from surmap.rpc.http_limits import (
    ClientDisconnected,
    RequestBodyTooLargeError,
    read_limited_body,
)


async def test_read_limited_body_joins_chunks() -> None:
    parts = [b"a", b"b", b"c"]
    index = 0

    async def receive() -> dict[str, object]:
        nonlocal index
        if index < len(parts):
            chunk = parts[index]
            index += 1
            return {"type": "http.request", "body": chunk, "more_body": index < len(parts)}
        raise AssertionError("unexpected receive")

    assert await read_limited_body(receive, max_bytes=10) == b"abc"


async def test_read_limited_body_rejects_oversized_payload() -> None:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"x" * 5, "more_body": False}

    with pytest.raises(RequestBodyTooLargeError):
        await read_limited_body(receive, max_bytes=3)


async def test_read_limited_body_stops_on_disconnect() -> None:
    async def receive() -> dict[str, object]:
        return {"type": "http.disconnect"}

    with pytest.raises(ClientDisconnected):
        await read_limited_body(receive)
