"""The REST binding as an ASGI application.

Routing reads the raw path (`raw_path`), not ASGI's decoded `path`: decoding is the template's
job, and a decoded path has already lost the difference between a `/` and an encoded `%2F`.

A server-streaming response that fails before its first message is an ordinary HTTP error; once
the first line has gone out the status is committed, so a later failure is a final NDJSON
`{"error": ...}` line.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from typing import Any, Protocol

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from google.protobuf.descriptor import MethodDescriptor
from google.protobuf.message import Message

from surmap.rpc.http_rule.codec import (
    NDJSON_CONTENT_TYPE,
    HttpRuleError,
    decode_request,
    encode_error,
    encode_response,
    encode_stream_error,
    encode_stream_result,
)
from surmap.rpc.http_rule.routes import HttpRuleRouter, RouteMatch

__all__ = ["HttpRuleApplication", "Invoker"]

_LOG = logging.getLogger(__name__)
_JSON = b"application/json"

Scope = Mapping[str, Any]
Receive = Callable[[], Awaitable[Mapping[str, Any]]]
Send = Callable[[Mapping[str, Any]], Awaitable[None]]


class Invoker(Protocol):
    """Runs a method — raises `connectrpc.errors.ConnectError` for a failure with a code."""

    async def unary(
        self, method: MethodDescriptor, request: Message, headers: Mapping[str, str]
    ) -> Message: ...

    def server_stream(
        self, method: MethodDescriptor, request: Message, headers: Mapping[str, str]
    ) -> AsyncIterator[Message]: ...


class _BodyTooLargeError(Exception):
    pass


class _ClientDisconnectedError(Exception):
    pass


class HttpRuleApplication:
    def __init__(self, router: HttpRuleRouter, invoker: Invoker, *, read_max_bytes: int) -> None:
        self._router = router
        self._invoker = invoker
        self._read_max_bytes = read_max_bytes

    def route_known(self, http_method: str, path: str) -> bool:
        """Whether this application owns the request — a matched rule or another verb."""
        if self._router.match(http_method, path) is not None:
            return True
        return bool(self._router.allowed_methods(path))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await _lifespan(receive, send)
            return
        if scope["type"] != "http":
            raise ValueError(f"unsupported ASGI scope type {scope['type']!r}")

        http_method = str(scope["method"]).upper()
        raw_path = scope.get("raw_path")
        if raw_path:
            path = raw_path.decode("latin-1")
        else:
            # ASGI `path` keeps `:` for verb routes; `quote` would turn `/v1/x:stream` into `%3A`.
            path = str(scope["path"])
        match = self._router.match(http_method, path)
        if match is None:
            allowed = self._router.allowed_methods(path)
            if allowed:
                await _send_error(
                    send,
                    Code.UNIMPLEMENTED,
                    f"{http_method} is not allowed on {path}",
                    status=405,
                    extra=[(b"allow", ", ".join(sorted(allowed)).encode())],
                )
            else:
                await _send_error(send, Code.NOT_FOUND, f"no route for {http_method} {path}")
            return

        try:
            body = await self._read_body(receive)
        except _ClientDisconnectedError:
            return
        except _BodyTooLargeError:
            await _send_error(
                send,
                Code.RESOURCE_EXHAUSTED,
                f"request body exceeds {self._read_max_bytes} bytes",
                status=413,
            )
            return

        query = bytes(scope.get("query_string", b"")).decode("latin-1")
        try:
            request = decode_request(
                match.binding, path_params=match.path_params, query=query, body=body
            )
        except HttpRuleError as error:
            await _send_error(send, error.code, error.message)
            return

        headers = _headers(scope)
        if match.binding.server_streaming:
            await self._stream(send, match, request, headers)
        else:
            await self._unary(send, match, request, headers)

    async def _read_body(self, receive: Receive) -> bytes:
        parts: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise _ClientDisconnectedError
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self._read_max_bytes:
                raise _BodyTooLargeError
            parts.append(chunk)
            if not message.get("more_body", False):
                break
        return b"".join(parts)

    async def _unary(
        self, send: Send, match: RouteMatch, request: Message, headers: Mapping[str, str]
    ) -> None:
        try:
            response = await self._invoker.unary(match.binding.method, request, headers)
        except ConnectError as error:
            await _send_connect_error(send, error)
            return
        except Exception:
            _LOG.exception("unary %s failed", match.binding.method.full_name)
            await _send_error(send, Code.INTERNAL, "internal error")
            return
        await _send(send, 200, _JSON, encode_response(match.binding, response))

    async def _stream(
        self, send: Send, match: RouteMatch, request: Message, headers: Mapping[str, str]
    ) -> None:
        messages = aiter(self._invoker.server_stream(match.binding.method, request, headers))
        try:
            try:
                first = await anext(messages)
            except StopAsyncIteration:
                await _send(send, 200, NDJSON_CONTENT_TYPE.encode(), b"")
                return
            except ConnectError as error:
                await _send_connect_error(send, error)
                return
            except Exception:
                _LOG.exception("stream %s failed", match.binding.method.full_name)
                await _send_error(send, Code.INTERNAL, "internal error")
                return

            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", NDJSON_CONTENT_TYPE.encode())],
                }
            )
            await _send_body(send, encode_stream_result(match.binding, first), more=True)
            try:
                async for message in messages:
                    await _send_body(send, encode_stream_result(match.binding, message), more=True)
            except ConnectError as error:
                body = encode_stream_error(error.code, error.message, error.details)
                await _send_body(send, body, more=True)
            except Exception:
                _LOG.exception("stream %s failed mid-stream", match.binding.method.full_name)
                await _send_body(
                    send, encode_stream_error(Code.INTERNAL, "internal error"), more=True
                )
            await _send_body(send, b"", more=False)
        finally:
            close = getattr(messages, "aclose", None)
            if close is not None:
                await close()


def _headers(scope: Scope) -> dict[str, str]:
    return {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in scope.get("headers", [])
    }


async def _lifespan(receive: Receive, send: Send) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def _send(
    send: Send,
    status: int,
    content_type: bytes,
    body: bytes,
    extra: list[tuple[bytes, bytes]] | None = None,
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", content_type), *(extra or [])],
        }
    )
    await _send_body(send, body, more=False)


async def _send_body(send: Send, body: bytes, *, more: bool) -> None:
    await send({"type": "http.response.body", "body": body, "more_body": more})


async def _send_error(
    send: Send,
    code: Code,
    message: str,
    *,
    status: int | None = None,
    extra: list[tuple[bytes, bytes]] | None = None,
    details: Iterable[object] = (),
) -> None:
    mapped_status, body = encode_error(code, message, details=details)
    await _send(send, status or mapped_status, _JSON, body, extra)


async def _send_connect_error(send: Send, error: ConnectError) -> None:
    mapped_status, body = encode_error(error.code, error.message, details=error.details)
    await _send(send, mapped_status, _JSON, body)
