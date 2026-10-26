"""Drive a connect-python application via the kit ASGI driver."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from connectrpc.server import ConnectASGIApplication

from surmap.rpc._asgi_internal import (
    CONNECT_PROTOCOL_VERSION,
    END_STREAM_FLAG,
    AsgiCollected,
    _connect_error_from_collected,
    endpoint_kind,
    unary_content_type,
)
from surmap.rpc._asgi_internal import (
    invoke_application as _invoke_application,
)

__all__ = [
    "CONNECT_PROTOCOL_VERSION",
    "END_STREAM_FLAG",
    "AsgiCollected",
    "_connect_error_from_collected",
    "endpoint_kind",
    "invoke_application",
    "unary_content_type",
    "unary_response_body",
]


def unary_response_body(collected: AsgiCollected) -> bytes:
    return b"".join(collected.body_chunks)


def _streaming_receive_live(incoming: object) -> Callable[[], Any]:
    """Feed an in-flight socket RPC call as request bytes arrive (bidi / client-stream)."""

    async def receive() -> dict[str, Any]:
        chunks = incoming.request_chunks  # type: ignore[attr-defined]
        while True:
            if chunks:
                chunk = chunks.pop(0)
                more = bool(chunks) or not incoming.ended  # type: ignore[attr-defined]
                return {"type": "http.request", "body": chunk, "more_body": more}
            if incoming.ended:  # type: ignore[attr-defined]
                return {"type": "http.request", "body": b"", "more_body": False}
            incoming.request_more.clear()  # type: ignore[attr-defined]
            await incoming.request_more.wait()  # type: ignore[attr-defined]

    return receive


async def invoke_application(
    app: ConnectASGIApplication[Any],
    *,
    path: str,
    headers: Mapping[str, str],
    request_body_chunks: list[bytes],
    on_body_chunk: Callable[[bytes], Awaitable[None]] | None = None,
    live_incoming: object | None = None,
) -> AsgiCollected:
    if live_incoming is not None:
        scope_headers = dict(headers)
        from surmap.rpc._asgi_internal import build_scope

        scope = build_scope(method="POST", path=path, headers=scope_headers)
        from surmap.rpc._asgi_internal import _AsgiCollector

        collector = _AsgiCollector(on_body_chunk=on_body_chunk)
        receive = _streaming_receive_live(live_incoming)
        await app(scope, receive, collector.send)
        return collector.collected

    return await _invoke_application(
        app,
        path=path,
        headers=headers,
        request_body_chunks=request_body_chunks,
        on_body_chunk=on_body_chunk,
        live_requests=None,
    )
