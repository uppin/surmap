"""Runs a method by calling the connect-python application that serves it, in process.

Dispatching through the application, rather than straight to a servicer, means interceptors,
permission checks and metrics run exactly as they do for a Connect call. The call is a Connect
protocol request in binary protobuf, delivered as a synthesized ASGI HTTP call:

- unary: `application/proto` in, the response message (or a JSON `{code, message}` error) out;
- server-streaming: `application/connect+proto` — one enveloped request message in, enveloped
  response messages out, ending with an end-of-stream envelope that carries any error.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from google.protobuf import message_factory
from google.protobuf.descriptor import MethodDescriptor
from google.protobuf.message import Message

from surmap.rpc._asgi_internal import (
    _connect_error_from_collected,
    invoke_application,
    method_path,
)

__all__ = ["ConnectAppInvoker"]

_END_STREAM = 0x02
_ENVELOPE_HEADER = 5
_STREAM_QUEUE_MAX = 16
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "content-encoding",
        "content-length",
        "content-type",
        "accept-encoding",
        "host",
        "keep-alive",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class ConnectAppInvoker:
    def __init__(self, applications: Mapping[str, Any]) -> None:
        """`applications`: connect-python ASGI applications, keyed by fully-qualified service."""
        self._applications = dict(applications)

    async def unary(
        self, method: MethodDescriptor, request: Message, headers: Mapping[str, str]
    ) -> Message:
        app = self._application(method)
        path = method_path(method.containing_service.full_name, method.name)
        call_headers = _call_headers(method, headers, "application/proto")
        collected = await invoke_application(
            app,
            path=path,
            headers=call_headers,
            request_body_chunks=[request.SerializeToString()],
        )
        connect_error = _connect_error_from_collected(collected)
        if connect_error is not None:
            raise connect_error
        body = b"".join(collected.body_chunks)
        return message_factory.GetMessageClass(method.output_type).FromString(body)

    async def server_stream(
        self, method: MethodDescriptor, request: Message, headers: Mapping[str, str]
    ) -> AsyncIterator[Message]:
        app = self._application(method)
        response_class = message_factory.GetMessageClass(method.output_type)
        payload = request.SerializeToString()
        chunks: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=_STREAM_QUEUE_MAX)
        finished = asyncio.Event()
        delivered = False

        async def receive() -> Mapping[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": _envelope(0, payload), "more_body": False}
            await finished.wait()
            return {"type": "http.disconnect"}

        async def send(message: Mapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                await chunks.put(("start", message["status"]))
            elif message["type"] == "http.response.body":
                await chunks.put(("body", message.get("body", b"")))

        async def run() -> None:
            try:
                await app(_scope(method, headers, "application/connect+proto"), receive, send)
            finally:
                await chunks.put(("done", None))

        task = asyncio.create_task(run())
        try:
            status = 200
            buffer = bytearray()
            while True:
                kind, value = await chunks.get()
                if kind == "start":
                    status = value
                    continue
                if kind == "done":
                    break
                buffer.extend(value)
                if status != 200:
                    continue
                while len(buffer) >= _ENVELOPE_HEADER:
                    length = int.from_bytes(buffer[1:5], "big")
                    if len(buffer) < _ENVELOPE_HEADER + length:
                        break
                    flags = buffer[0]
                    frame = bytes(buffer[_ENVELOPE_HEADER : _ENVELOPE_HEADER + length])
                    del buffer[: _ENVELOPE_HEADER + length]
                    if flags & _END_STREAM:
                        _raise_end_of_stream_error(frame)
                        return
                    yield response_class.FromString(frame)
            if status != 200:
                raise _error_from_json(bytes(buffer), status)
            raise ConnectError(Code.INTERNAL, "stream ended without an end-of-stream message")
        finally:
            finished.set()
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _application(self, method: MethodDescriptor) -> Any:
        service = method.containing_service.full_name
        app = self._applications.get(service)
        if app is None:
            raise ConnectError(Code.UNIMPLEMENTED, f"no application serves {service}")
        return app


def _call_headers(
    method: MethodDescriptor, headers: Mapping[str, str], content_type: str
) -> dict[str, str]:
    forwarded = {
        name: value
        for name, value in headers.items()
        if name.lower() not in _HOP_BY_HOP
    }
    return {
        "content-type": content_type,
        "connect-protocol-version": "1",
        **forwarded,
    }


def _scope(
    method: MethodDescriptor, headers: Mapping[str, str], content_type: str
) -> dict[str, Any]:
    forwarded = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in headers.items()
        if name.lower() not in _HOP_BY_HOP
    ]
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "2",
        "method": "POST",
        "scheme": "http",
        "path": f"/{method.containing_service.full_name}/{method.name}",
        "raw_path": f"/{method.containing_service.full_name}/{method.name}".encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"content-type", content_type.encode()),
            (b"connect-protocol-version", b"1"),
            *forwarded,
        ],
        "client": None,
        "server": None,
        "extensions": {},
    }



def _envelope(flags: int, payload: bytes) -> bytes:
    return bytes([flags]) + len(payload).to_bytes(4, "big") + payload


def _code_of(value: object) -> Code:
    try:
        return Code(value)
    except ValueError:
        return Code.UNKNOWN


def _error_from_json(body: bytes, status: int) -> ConnectError:
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return ConnectError(Code.UNKNOWN, f"HTTP {status} without a Connect error body")
    return ConnectError(_code_of(payload.get("code")), str(payload.get("message", "")))


def _raise_end_of_stream_error(frame: bytes) -> None:
    payload = json.loads(frame or b"{}")
    error = payload.get("error")
    if error:
        raise ConnectError(_code_of(error.get("code")), str(error.get("message", "")))
