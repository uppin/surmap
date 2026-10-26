"""In-process Connect ASGI driving — adapted from the compute-agent socket RPC layer."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from connectrpc._compression import IdentityCompression
from connectrpc._protocol import ConnectWireError
from connectrpc._protocol_connect import (
    CONNECT_UNARY_CONTENT_TYPE_PREFIX,
    ConnectEnvelopeReader,
    ConnectEnvelopeWriter,
)
from connectrpc._server_shared import (
    EndpointBidiStream,
    EndpointClientStream,
    EndpointServerStream,
    EndpointUnary,
)
from connectrpc.code import Code
from connectrpc.compat import google_protobuf_codecs
from connectrpc.errors import ConnectError
from connectrpc.server import ConnectASGIApplication
from google.protobuf.message import Message

CONNECT_PROTOCOL_VERSION = "1"
END_STREAM_FLAG = 0x02

_DEFAULT_CODEC = google_protobuf_codecs()[0]


def build_scope(
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
    query_string: bytes = b"",
) -> dict[str, Any]:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "scheme": "http",
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers.items()],
        "query_string": query_string,
        "client": ("127.0.0.1", 0),
        "extensions": {},
    }


@dataclass
class AsgiCollected:
    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body_chunks: list[bytes] = field(default_factory=list)


class _AsgiCollector:
    def __init__(
        self,
        *,
        on_body_chunk: Callable[[bytes], Awaitable[None]] | None = None,
    ) -> None:
        self._result = AsgiCollected()
        self._on_body_chunk = on_body_chunk

    async def send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self._result.status = message["status"]
            for name, value in message.get("headers", ()):
                self._result.headers[name.decode().lower()] = value.decode()
        elif message["type"] == "http.response.body":
            chunk = message.get("body", b"")
            self._result.body_chunks.append(chunk)
            if self._on_body_chunk is not None and chunk:
                await self._on_body_chunk(chunk)

    @property
    def collected(self) -> AsgiCollected:
        return self._result


class _LiveRequestStream:
    """Feeds request bytes to ASGI `receive` as a producer pushes them."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._ended = False
        self._more = asyncio.Event()

    def push(self, chunk: bytes, *, end: bool = False) -> None:
        self._chunks.append(chunk)
        if end:
            self._ended = True
        self._more.set()

    def finish(self) -> None:
        self._ended = True
        self._more.set()

    def receive(self) -> Callable[[], Any]:
        async def _receive() -> dict[str, Any]:
            while True:
                if self._chunks:
                    chunk = self._chunks.pop(0)
                    more = bool(self._chunks) or not self._ended
                    return {"type": "http.request", "body": chunk, "more_body": more}
                if self._ended:
                    return {"type": "http.request", "body": b"", "more_body": False}
                self._more.clear()
                await self._more.wait()

        return _receive


def _streaming_receive(chunks: list[bytes]) -> Callable[[], Any]:
    index = 0

    async def receive() -> dict[str, Any]:
        nonlocal index
        if index < len(chunks):
            chunk = chunks[index]
            index += 1
            more = index < len(chunks)
            return {"type": "http.request", "body": chunk, "more_body": more}
        if not chunks:
            return {"type": "http.request", "body": b"", "more_body": False}
        await _never_disconnect()
        return {"type": "http.disconnect"}

    return receive


async def _never_disconnect() -> None:
    await asyncio.Event().wait()


def _unary_receive(body: bytes) -> Callable[[], Any]:
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await _never_disconnect()
        return {"type": "http.disconnect"}

    return receive


def _connect_error_from_collected(collected: AsgiCollected) -> ConnectError | None:
    if collected.status is None:
        return ConnectError(Code.INTERNAL, "application finished without sending a response")
    if collected.status == HTTPStatus.OK:
        return None
    body = b"".join(collected.body_chunks)
    if body:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and "code" in data:
            return ConnectWireError.from_dict(data, collected.status, Code.UNKNOWN).to_exception()
    if collected.status == HTTPStatus.NOT_FOUND:
        return ConnectError(Code.UNIMPLEMENTED, "unimplemented")
    return ConnectWireError.from_http_status(collected.status).to_exception()


def _is_streaming_endpoint(app: ConnectASGIApplication[Any], path: str) -> bool:
    endpoints = app._resolve_endpoints(app._service)
    endpoint = endpoints.get(path)
    if endpoint is None:
        return False
    return not isinstance(endpoint, EndpointUnary)


async def invoke_application(
    app: ConnectASGIApplication[Any],
    *,
    path: str,
    headers: Mapping[str, str],
    request_body_chunks: list[bytes],
    on_body_chunk: Callable[[bytes], Awaitable[None]] | None = None,
    live_requests: _LiveRequestStream | None = None,
) -> AsgiCollected:
    scope = build_scope(method="POST", path=path, headers=headers)
    collector = _AsgiCollector(on_body_chunk=on_body_chunk)
    if live_requests is not None:
        receive = live_requests.receive()
    elif _is_streaming_endpoint(app, path):
        receive = _streaming_receive(request_body_chunks)
    else:
        receive = _unary_receive(b"".join(request_body_chunks))
    await app(scope, receive, collector.send)
    return collector.collected


def unary_content_type(codec_name: str) -> str:
    return f"{CONNECT_UNARY_CONTENT_TYPE_PREFIX}{codec_name}"


def streaming_content_type(codec_name: str) -> str:
    return f"application/connect+{codec_name}"


def default_call_headers(*, streaming: bool) -> dict[str, str]:
    codec_name = _DEFAULT_CODEC.name()
    if streaming:
        content_type = streaming_content_type(codec_name)
    else:
        content_type = unary_content_type(codec_name)
    return {
        "connect-protocol-version": CONNECT_PROTOCOL_VERSION,
        "content-type": content_type,
    }


def method_path(service_name: str, method_name: str) -> str:
    return f"/{service_name}/{method_name}"


def decode_unary_body(body: bytes, message_class: type[Message]) -> Message:
    if not body:
        return message_class.FromString(b"")
    try:
        return message_class.FromString(body)
    except Exception:
        reader = ConnectEnvelopeReader(message_class, _DEFAULT_CODEC, IdentityCompression(), None)
        last: Message | None = None
        offset = 0
        while offset < len(body):
            flags = body[offset]
            length = int.from_bytes(body[offset + 1 : offset + 5], "big")
            chunk = body[offset : offset + 5 + length]
            offset += 5 + length
            for message in reader.feed(chunk):
                last = message
            if flags & END_STREAM_FLAG:
                break
        if last is None:
            raise ConnectError(Code.INTERNAL, "call returned no response message") from None
        return last


async def iter_stream_messages(
    body_chunks: AsyncIterable[bytes] | list[bytes],
    *,
    message_class: type[Message],
) -> AsyncIterator[Message]:
    reader = ConnectEnvelopeReader(message_class, _DEFAULT_CODEC, IdentityCompression(), None)
    if isinstance(body_chunks, list):
        chunks: AsyncIterable[bytes] = _iter_list(body_chunks)
    else:
        chunks = body_chunks
    async for chunk in chunks:
        for message in reader.feed(chunk):
            yield message


async def _iter_list(items: list[bytes]) -> AsyncIterator[bytes]:
    for item in items:
        yield item


def encode_stream_request(request: Message) -> bytes:
    writer = ConnectEnvelopeWriter(_DEFAULT_CODEC, IdentityCompression())
    return writer.write(request)


async def stream_response_body_chunks(
    app: ConnectASGIApplication[Any],
    *,
    path: str,
    headers: Mapping[str, str],
    request_body_chunks: list[bytes],
    live_requests: _LiveRequestStream | None = None,
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[bytes | None | BaseException] = asyncio.Queue()
    collected_holder: list[AsgiCollected] = []

    async def on_chunk(chunk: bytes) -> None:
        await queue.put(chunk)

    async def run() -> None:
        try:
            collected = await invoke_application(
                app,
                path=path,
                headers=headers,
                request_body_chunks=request_body_chunks,
                on_body_chunk=on_chunk,
                live_requests=live_requests,
            )
            collected_holder.append(collected)
        except BaseException as error:
            await queue.put(error)
        finally:
            await queue.put(None)

    runner = asyncio.create_task(run())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        await runner

    if not collected_holder:
        return
    error = _connect_error_from_collected(collected_holder[0])
    if error is not None:
        raise error


async def feed_live_requests(live: _LiveRequestStream, requests: AsyncIterable[Message]) -> None:
    async for item in requests:
        live.push(encode_stream_request(item), end=False)
    live.finish()


_ENDPOINT_KINDS: dict[type, str] = {
    EndpointUnary: "unary",
    EndpointServerStream: "server_stream",
    EndpointClientStream: "client_stream",
    EndpointBidiStream: "bidi",
}


def endpoint_kind(app: ConnectASGIApplication[Any], path: str) -> str:
    endpoints = app._resolve_endpoints(app._service)
    endpoint = endpoints.get(path)
    if endpoint is None:
        return "unknown"
    return _ENDPOINT_KINDS.get(type(endpoint), "unknown")
