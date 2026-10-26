"""Drive a connect-python application in process: one synthesized ASGI call per RPC, no socket."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from typing import Any

from connectrpc.compat import google_protobuf_codecs
from google.protobuf.descriptor import MethodDescriptor
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessageClass

from surmap.rpc._asgi_internal import (
    _connect_error_from_collected,
    _LiveRequestStream,
    decode_unary_body,
    default_call_headers,
    encode_stream_request,
    feed_live_requests,
    invoke_application,
    iter_stream_messages,
    method_path,
    stream_response_body_chunks,
)

__all__ = ["call_bidi", "call_client_stream", "call_server_stream", "call_unary"]

_CODEC = google_protobuf_codecs()[0]


def _output_class(method: MethodDescriptor) -> type[Message]:
    return GetMessageClass(method.output_type)


def _service_name(method: MethodDescriptor) -> str:
    return method.containing_service.full_name


async def call_unary(
    app: Any, method: MethodDescriptor, request: Message, headers: Mapping[str, str] | None = None
) -> Message:
    """Raises `connectrpc.errors.ConnectError` with the handler's code on failure."""
    path = method_path(_service_name(method), method.name)
    body = _CODEC.encode(request)
    call_headers = dict(default_call_headers(streaming=False))
    if headers:
        call_headers.update(headers)
    collected = await invoke_application(
        app, path=path, headers=call_headers, request_body_chunks=[body]
    )
    error = _connect_error_from_collected(collected)
    if error is not None:
        raise error
    response_body = b"".join(collected.body_chunks)
    return decode_unary_body(response_body, _output_class(method))


def call_server_stream(
    app: Any, method: MethodDescriptor, request: Message, headers: Mapping[str, str] | None = None
) -> AsyncIterator[Message]:
    path = method_path(_service_name(method), method.name)
    body = encode_stream_request(request)
    call_headers = dict(default_call_headers(streaming=True))
    if headers:
        call_headers.update(headers)

    async def _gen() -> AsyncIterator[Message]:
        output = _output_class(method)
        chunks = stream_response_body_chunks(
            app, path=path, headers=call_headers, request_body_chunks=[body]
        )
        async for message in iter_stream_messages(chunks, message_class=output):
            yield message

    return _gen()


async def call_client_stream(
    app: Any,
    method: MethodDescriptor,
    requests: AsyncIterable[Message],
    headers: Mapping[str, str] | None = None,
) -> Message:
    path = method_path(_service_name(method), method.name)
    live = _LiveRequestStream()
    call_headers = dict(default_call_headers(streaming=True))
    if headers:
        call_headers.update(headers)

    feeder = asyncio.create_task(feed_live_requests(live, requests))
    collected = await invoke_application(
        app,
        path=path,
        headers=call_headers,
        request_body_chunks=[],
        live_requests=live,
    )
    await feeder
    error = _connect_error_from_collected(collected)
    if error is not None:
        raise error
    response_body = b"".join(collected.body_chunks)
    return decode_unary_body(response_body, _output_class(method))


def call_bidi(
    app: Any,
    method: MethodDescriptor,
    requests: AsyncIterable[Message],
    headers: Mapping[str, str] | None = None,
) -> AsyncIterator[Message]:
    path = method_path(_service_name(method), method.name)
    call_headers = dict(default_call_headers(streaming=True))
    if headers:
        call_headers.update(headers)

    async def _gen() -> AsyncIterator[Message]:
        live = _LiveRequestStream()
        feeder = asyncio.create_task(feed_live_requests(live, requests))
        output = _output_class(method)
        try:
            chunks = stream_response_body_chunks(
                app,
                path=path,
                headers=call_headers,
                request_body_chunks=[],
                live_requests=live,
            )
            async for message in iter_stream_messages(chunks, message_class=output):
                yield message
        finally:
            await feeder

    return _gen()
