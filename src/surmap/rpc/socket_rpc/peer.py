"""One end of a Connect-over-WebSocket socket: it serves, and it calls."""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, TypeVar, cast

from connectrpc._compression import IdentityCompression
from connectrpc._protocol import ConnectWireError
from connectrpc._protocol_connect import ConnectEnvelopeReader, ConnectEnvelopeWriter
from connectrpc.code import Code
from connectrpc.compat import google_protobuf_codecs
from connectrpc.errors import ConnectError
from connectrpc.method import MethodInfo
from connectrpc.server import ConnectASGIApplication
from google.protobuf.message import Message

from surmap.rpc.socket_rpc._asgi import (
    CONNECT_PROTOCOL_VERSION,
    END_STREAM_FLAG,
    _connect_error_from_collected,
    endpoint_kind,
    invoke_application,
    unary_content_type,
    unary_response_body,
)
from surmap.rpc.socket_rpc._trace import socket_debug, socket_trace
from surmap.rpc.socket_rpc._wire import (
    bytes_field,
    decode_frame,
    encode_frame,
    error_from_socket,
    headers_from_metadata,
    message_bytes,
    metadata_from_headers,
    socket_error,
)
from surmap.transport.v1 import socket_rpc_pb2

__all__ = ["FrameSocket", "PeerRole", "SocketRpcError", "SocketRpcPeer"]

REQ = TypeVar("REQ", bound=Message)
RES = TypeVar("RES", bound=Message)

_DEFAULT_CODEC = google_protobuf_codecs()[0]

# A body travels as frames of at most this many payload bytes, so no frame nears a WebSocket
# message limit (1 MiB by default) however large the body is.
DEFAULT_CHUNK_BYTES = 256 * 1024
# What a receiver buffers for one call before refusing it; a refused call fails alone.
DEFAULT_MAX_CALL_BYTES = 64 * 1024 * 1024

_unary_request_body: contextvars.ContextVar[bytes | None] = contextvars.ContextVar(
    "socket_rpc_unary_request_body", default=None
)


def unary_request_body_for_verify() -> bytes | None:
    """Wire body for the unary call currently being dispatched, if any."""
    return _unary_request_body.get()


class FrameSocket(Protocol):
    """The socket a peer runs over: binary frames in, binary frames out."""

    async def send(self, frame: bytes) -> None: ...

    async def recv(self) -> bytes:
        """The next frame; raises when the socket has closed."""
        ...

    async def close(self) -> None: ...


class PeerRole(Enum):
    """Which end of the socket this peer is — it decides the parity of the stream ids it opens."""

    DIALER = "dialer"
    """Opened the socket; its calls use odd stream ids."""

    ACCEPTOR = "acceptor"
    """Accepted the socket; its calls use even stream ids."""


class SocketRpcError(Exception):
    """A call failed: the called peer's Connect error, or a transport failure."""

    def __init__(self, code: Code, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class _IncomingCall:
    stream_id: int
    init: socket_rpc_pb2.CallInit
    request_chunks: list[bytes] = field(default_factory=list)
    buffered_bytes: int = 0
    ended: bool = False
    aborted: bool = False
    task: asyncio.Task[None] | None = None
    request_more: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class _OutgoingCall:
    stream_id: int
    method: MethodInfo[Any, Any]
    kind: str
    response_queue: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    error: SocketRpcError | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    response_body: bytearray = field(default_factory=bytearray)
    buffer_body: bool = True
    headers_sent: bool = False
    finished: bool = False


class SocketRpcPeer:
    """Serves `applications` to the other end of `socket`, and calls methods on it."""

    def __init__(
        self,
        socket: FrameSocket,
        *,
        role: PeerRole,
        applications: Mapping[str, ConnectASGIApplication[Any]] | None = None,
        chunk_size: int = DEFAULT_CHUNK_BYTES,
        max_call_bytes: int = DEFAULT_MAX_CALL_BYTES,
    ) -> None:
        """`applications` are keyed by fully-qualified service name. `chunk_size` bounds the
        payload of one frame; `max_call_bytes` bounds what is buffered for one call."""
        self._socket = socket
        self._role = role
        self._chunk_size = chunk_size
        self._max_call_bytes = max_call_bytes
        self._applications = dict(applications or {})
        self._next_id = 1 if role == PeerRole.DIALER else 2
        self._id_step = 2
        self._send_lock = asyncio.Lock()
        self._closed = False
        self._close_event = asyncio.Event()
        self._incoming: dict[int, _IncomingCall] = {}
        self._outgoing: dict[int, _OutgoingCall] = {}
        self._serve_guard = asyncio.Lock()

    @property
    def role(self) -> PeerRole:
        return self._role

    def next_stream_id(self) -> int:
        """Reserve the id of the next call this peer starts."""
        stream_id = self._next_id
        self._next_id += self._id_step
        return stream_id

    async def serve(self, *, when_ready: asyncio.Event | None = None) -> None:
        """Read frames until the socket closes, answering calls and routing responses."""
        socket_trace("socket_rpc.serve.enter", role=self._role.value)
        if when_ready is not None:
            when_ready.set()
        try:
            while not self._closed:
                try:
                    raw = await self._socket.recv()
                except ConnectionError:
                    break
                try:
                    frame = decode_frame(raw)
                except ValueError:
                    await self._fail_all_open_calls(Code.UNAVAILABLE, "malformed socket frame")
                    break
                kind = frame.WhichOneof("kind")
                if kind == "request":
                    await self._handle_request(frame.request)
                elif kind == "response":
                    await self._handle_response(frame.response)
        finally:
            socket_trace("socket_rpc.serve.exit", role=self._role.value)
            self._closed = True
            self._close_event.set()
            await self._fail_all_open_calls(Code.UNAVAILABLE, "socket closed")

    def _incoming_endpoint_kind(self, incoming: _IncomingCall) -> str:
        service_name = incoming.init.service_name.value
        method_name = incoming.init.method_name.value
        app = self._applications.get(service_name)
        if app is None:
            return "unknown"
        path = f"/{service_name}/{method_name}"
        return endpoint_kind(app, path)

    def _append_incoming_request(self, incoming: _IncomingCall, chunk: bytes) -> bool:
        """False when the call was refused for holding more than `max_call_bytes`."""
        if chunk:
            incoming.request_chunks.append(chunk)
            incoming.buffered_bytes += len(chunk)
        # A dispatched call consumes its chunks as they arrive, so only a call still waiting for
        # its whole body is buffering it.
        if incoming.task is None and incoming.buffered_bytes > self._max_call_bytes:
            return False
        if incoming.task is not None:
            incoming.request_more.set()
        return True

    async def _refuse_oversized_call(self, stream_id: int) -> None:
        self._incoming.pop(stream_id, None)
        await self._send_response_error(
            stream_id,
            Code.RESOURCE_EXHAUSTED,
            f"call body exceeds {self._max_call_bytes} bytes",
        )

    def _start_incoming_dispatch(self, incoming: _IncomingCall) -> None:
        if incoming.task is not None:
            return
        incoming.task = asyncio.create_task(self._dispatch_incoming(incoming))

    async def _handle_request(self, request: socket_rpc_pb2.SocketRequest) -> None:
        stream_id = request.stream_id
        if request.abort:
            incoming = self._incoming.get(stream_id)
            if incoming is None:
                return
            incoming.aborted = True
            if incoming.task:
                incoming.task.cancel()
            else:
                self._incoming.pop(stream_id, None)
            return

        if request.HasField("call_init"):
            init = request.call_init
            incoming = _IncomingCall(stream_id=stream_id, init=init)
            self._incoming[stream_id] = incoming
            if request.end_of_stream:
                incoming.ended = True
            if not self._append_incoming_request(incoming, message_bytes(request.message)):
                await self._refuse_oversized_call(stream_id)
                return
            kind = self._incoming_endpoint_kind(incoming)
            socket_trace(
                "socket_rpc.call_init",
                stream_id=stream_id,
                service=init.service_name.value,
                method=init.method_name.value,
                kind=kind,
                role=self._role.value,
            )
            if kind in {"bidi", "client_stream"} or incoming.ended:
                self._start_incoming_dispatch(incoming)
            return

        incoming = self._incoming.get(stream_id)
        if incoming is None:
            return
        if request.end_of_stream:
            incoming.ended = True
        if not self._append_incoming_request(incoming, message_bytes(request.message)):
            await self._refuse_oversized_call(stream_id)
            return
        if incoming.task is None and incoming.ended:
            self._start_incoming_dispatch(incoming)

    async def _handle_response(self, response: socket_rpc_pb2.SocketResponse) -> None:
        stream_id = response.stream_id
        outgoing = self._outgoing.get(stream_id)
        if outgoing is None or outgoing.finished:
            return
        if response.error.code:
            code, message = error_from_socket(response.error)
            outgoing.error = SocketRpcError(code, message)
            socket_debug(
                "socket_rpc.outgoing_error",
                stream_id=stream_id,
                method=outgoing.method.name,
                service=outgoing.method.service_name,
                code=code.name,
                message=message,
                role=self._role.value,
            )
            outgoing.finished = True
            outgoing.done.set()
            await outgoing.response_queue.put(None)
            return
        payload = message_bytes(response.message)
        if (
            outgoing.buffer_body
            and len(outgoing.response_body) + len(payload) > self._max_call_bytes
        ):
            outgoing.error = SocketRpcError(
                Code.RESOURCE_EXHAUSTED, f"call response exceeds {self._max_call_bytes} bytes"
            )
            outgoing.finished = True
            outgoing.done.set()
            await outgoing.response_queue.put(None)
            await self._send_abort(stream_id)
            return
        if payload:
            if outgoing.buffer_body:
                outgoing.response_body.extend(payload)
            await outgoing.response_queue.put(payload)
        if response.end_of_stream:
            outgoing.finished = True
            outgoing.done.set()
            await outgoing.response_queue.put(None)

    async def _dispatch_incoming(self, incoming: _IncomingCall) -> None:
        service_name = incoming.init.service_name.value
        method_name = incoming.init.method_name.value
        socket_trace(
            "socket_rpc.dispatch.start",
            stream_id=incoming.stream_id,
            service=service_name,
            method=method_name,
        )
        app = self._applications.get(service_name)
        path = f"/{service_name}/{method_name}"
        headers = headers_from_metadata(incoming.init.metadata)
        headers.setdefault("connect-protocol-version", CONNECT_PROTOCOL_VERSION)
        if incoming.init.timeout_ms.value:
            headers["connect-timeout-ms"] = str(incoming.init.timeout_ms.value)

        body_token: contextvars.Token[bytes | None] | None = None
        try:
            if app is None:
                await self._send_response_error(
                    incoming.stream_id, Code.UNIMPLEMENTED, f"unknown service {service_name}"
                )
                return

            kind = endpoint_kind(app, path)
            if kind == "unknown":
                await self._send_response_error(
                    incoming.stream_id, Code.UNIMPLEMENTED, f"unknown method {method_name}"
                )
                return

            body = b"".join(incoming.request_chunks)
            if kind == "unary":
                headers["content-type"] = unary_content_type(_DEFAULT_CODEC.name())
            else:
                headers["content-type"] = f"application/connect+{_DEFAULT_CODEC.name()}"

            if kind == "unary":
                body_token = _unary_request_body.set(body)

            stream_buffer = bytearray()
            stream_offset = 0
            stream_ended = False

            async def _emit_connect_chunks() -> None:
                nonlocal stream_offset, stream_ended
                while stream_offset + 5 <= len(stream_buffer):
                    flags = stream_buffer[stream_offset]
                    length = int.from_bytes(
                        stream_buffer[stream_offset + 1 : stream_offset + 5], "big"
                    )
                    if stream_offset + 5 + length > len(stream_buffer):
                        return
                    chunk = bytes(stream_buffer[stream_offset : stream_offset + 5 + length])
                    stream_offset += 5 + length
                    end = bool(flags & END_STREAM_FLAG)
                    await self._send_response_message(incoming.stream_id, chunk, end=end)
                    if end:
                        stream_ended = True
                        return

            async def on_body_chunk(chunk: bytes) -> None:
                stream_buffer.extend(chunk)
                await _emit_connect_chunks()

            collected = await invoke_application(
                app,
                path=path,
                headers=headers,
                request_body_chunks=[body] if body else [],
                on_body_chunk=on_body_chunk if kind in {"server_stream", "bidi"} else None,
                live_incoming=incoming if kind in {"bidi", "client_stream"} else None,
            )
            connect_error = _connect_error_from_collected(collected)
            if connect_error is not None:
                await self._send_response_error(
                    incoming.stream_id, connect_error.code, connect_error.message
                )
                return

            response_bytes = unary_response_body(collected)
            content_type = collected.headers.get("content-type", "")
            if kind in {"server_stream", "bidi"} or content_type.startswith("application/connect+"):
                if response_bytes:
                    stream_buffer.extend(response_bytes)
                    await _emit_connect_chunks()
                if not stream_ended:
                    await self._send_response_message(incoming.stream_id, b"", end=True)
            else:
                await self._send_response_message(incoming.stream_id, response_bytes, end=True)
        except asyncio.CancelledError:
            await self._send_response_error(incoming.stream_id, Code.CANCELED, "call aborted")
            raise
        except ConnectError as error:
            socket_debug(
                "socket_rpc.handler_error",
                stream_id=incoming.stream_id,
                service=service_name,
                method=method_name,
                code=error.code.name,
                message=error.message,
                role=self._role.value,
            )
            await self._send_response_error(incoming.stream_id, error.code, error.message)
        except Exception as error:
            wire = ConnectWireError.from_exception(error)
            await self._send_response_error(incoming.stream_id, wire.code, wire.message)
        finally:
            if body_token is not None:
                _unary_request_body.reset(body_token)
            self._incoming.pop(incoming.stream_id, None)

    async def _send_frame(self, frame: socket_rpc_pb2.SocketFrame) -> None:
        if self._closed:
            raise SocketRpcError(Code.UNAVAILABLE, "peer closed")
        async with self._send_lock:
            await self._socket.send(encode_frame(frame))

    def _chunks(self, body: bytes) -> list[bytes]:
        """`body` as frame payloads of at most `chunk_size`; an empty body is one empty payload."""
        if not body:
            return [b""]
        return [
            body[start : start + self._chunk_size]
            for start in range(0, len(body), self._chunk_size)
        ]

    @staticmethod
    async def _let_other_calls_send(chunk_index: int) -> None:
        """A socket whose `send` does not suspend (the gRPC transport's queue) would otherwise let
        one large body take the send lock for all of its chunks."""
        if chunk_index:
            await asyncio.sleep(0)

    async def _send_response_message(self, stream_id: int, payload: bytes, *, end: bool) -> None:
        chunks = self._chunks(payload)
        for index, chunk in enumerate(chunks):
            await self._let_other_calls_send(index)
            response = socket_rpc_pb2.SocketResponse(
                stream_id=stream_id, end_of_stream=end and index == len(chunks) - 1
            )
            response.message.CopyFrom(bytes_field(chunk))
            await self._send_frame(socket_rpc_pb2.SocketFrame(response=response))

    async def _send_response_error(self, stream_id: int, code: Code, message: str) -> None:
        response = socket_rpc_pb2.SocketResponse(
            stream_id=stream_id,
            end_of_stream=True,
            error=socket_error(code, message),
        )
        await self._send_frame(socket_rpc_pb2.SocketFrame(response=response))

    def _method_path(self, method: MethodInfo[REQ, RES]) -> str:
        return f"/{method.service_name}/{method.name}"

    def _call_kind(self, method: MethodInfo[REQ, RES]) -> str:
        app = self._applications.get(method.service_name)
        if app is None:
            return "unary"
        return endpoint_kind(app, self._method_path(method))

    async def call_unary(
        self,
        method: MethodInfo[REQ, RES],
        request: REQ,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_ms: int | None = None,
    ) -> RES:
        body = _DEFAULT_CODEC.encode(request)
        return await self.call_unary_with_body(method, body, headers=headers, timeout_ms=timeout_ms)

    async def call_unary_with_body(
        self,
        method: MethodInfo[REQ, RES],
        request_body: bytes,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_ms: int | None = None,
    ) -> RES:
        collected = await self._round_trip(
            method,
            request_bodies=[request_body],
            headers=headers,
            timeout_ms=timeout_ms,
            stream=False,
        )
        return cast(RES, _DEFAULT_CODEC.decode(collected, method.output))

    def call_server_stream(
        self,
        method: MethodInfo[REQ, RES],
        request: REQ,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_ms: int | None = None,
    ) -> AsyncIterator[RES]:
        writer = ConnectEnvelopeWriter(_DEFAULT_CODEC, IdentityCompression())

        async def _gen() -> AsyncIterator[RES]:
            body = writer.write(request)
            async for message in self._stream_round_trip(
                method,
                request_bodies=[body],
                headers=headers,
                timeout_ms=timeout_ms,
            ):
                yield message

        return _gen()

    async def call_client_stream(
        self,
        method: MethodInfo[REQ, RES],
        requests: AsyncIterable[REQ],
        *,
        headers: Mapping[str, str] | None = None,
        timeout_ms: int | None = None,
    ) -> RES:
        writer = ConnectEnvelopeWriter(_DEFAULT_CODEC, IdentityCompression())
        stream_id = self.next_stream_id()
        outgoing = _OutgoingCall(stream_id=stream_id, method=method, kind=self._call_kind(method))
        self._outgoing[stream_id] = outgoing
        try:
            await self._send_call_open(
                stream_id,
                method,
                headers=headers,
                timeout_ms=timeout_ms,
                first_body=b"",
                end=False,
            )
            async for item in self._requests_until_close(requests, stop_when=outgoing.done):
                await self._send_call_data(stream_id, writer.write(item), end=False)
            await self._send_call_data(stream_id, b"", end=True)
            await self._wait_for_outgoing(outgoing, timeout_ms)
            if outgoing.error is not None:
                raise outgoing.error from None
            return cast(
                RES,
                _DEFAULT_CODEC.decode(
                    _decode_unary_response_body(bytes(outgoing.response_body), method.output),
                    method.output,
                ),
            )
        finally:
            self._outgoing.pop(stream_id, None)

    def call_bidi_stream(
        self,
        method: MethodInfo[REQ, RES],
        requests: AsyncIterable[REQ],
        *,
        headers: Mapping[str, str] | None = None,
        timeout_ms: int | None = None,
    ) -> AsyncIterator[RES]:
        writer = ConnectEnvelopeWriter(_DEFAULT_CODEC, IdentityCompression())

        async def _gen() -> AsyncIterator[RES]:
            stream_id = self.next_stream_id()
            outgoing = _OutgoingCall(
                stream_id=stream_id,
                method=method,
                kind=self._call_kind(method),
                buffer_body=False,
            )
            self._outgoing[stream_id] = outgoing
            reader = ConnectEnvelopeReader(
                method.output, _DEFAULT_CODEC, IdentityCompression(), None
            )

            async def _send_requests() -> None:
                try:
                    await self._send_call_open(
                        stream_id,
                        method,
                        headers=headers,
                        timeout_ms=timeout_ms,
                        first_body=b"",
                        end=False,
                    )
                    async for item in requests:
                        await self._send_call_data(stream_id, writer.write(item), end=False)
                    await self._send_call_data(stream_id, b"", end=True)
                except Exception:
                    outgoing.done.set()

            sender = asyncio.create_task(_send_requests())
            try:
                while True:
                    chunk = await outgoing.response_queue.get()
                    if chunk is None:
                        if outgoing.error is not None:
                            raise outgoing.error from None
                        break
                    try:
                        for message in reader.feed(chunk):
                            yield message
                    except ConnectError as error:
                        raise SocketRpcError(error.code, error.message) from error
            finally:
                sender.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sender
                await self._send_abort(stream_id)
                self._outgoing.pop(stream_id, None)

        return _gen()

    async def _round_trip(
        self,
        method: MethodInfo[REQ, RES],
        *,
        request_bodies: list[bytes],
        headers: Mapping[str, str] | None,
        timeout_ms: int | None,
        stream: bool,
    ) -> bytes:
        stream_id = self.next_stream_id()
        outgoing = _OutgoingCall(stream_id=stream_id, method=method, kind=self._call_kind(method))
        self._outgoing[stream_id] = outgoing
        try:
            await self._send_call_open(
                stream_id,
                method,
                headers=headers,
                timeout_ms=timeout_ms,
                first_body=request_bodies[0] if request_bodies else b"",
                end=len(request_bodies) <= 1,
            )
            for chunk in request_bodies[1:]:
                await self._send_call_data(stream_id, chunk, end=False)
            if len(request_bodies) > 1:
                await self._send_call_data(stream_id, b"", end=True)
            await self._wait_for_outgoing(outgoing, timeout_ms)
            if outgoing.error is not None:
                raise outgoing.error from None
            body = bytes(outgoing.response_body)
            if stream:
                return _unary_from_stream_body(body, method.output)
            return _decode_unary_response_body(body, method.output)
        finally:
            self._outgoing.pop(stream_id, None)

    async def _stream_round_trip(
        self,
        method: MethodInfo[REQ, RES],
        *,
        request_bodies: list[bytes],
        headers: Mapping[str, str] | None,
        timeout_ms: int | None,
    ) -> AsyncIterator[RES]:
        stream_id = self.next_stream_id()
        outgoing = _OutgoingCall(
            stream_id=stream_id,
            method=method,
            kind=self._call_kind(method),
            buffer_body=False,
        )
        self._outgoing[stream_id] = outgoing
        try:
            await self._send_call_open(
                stream_id,
                method,
                headers=headers,
                timeout_ms=timeout_ms,
                first_body=request_bodies[0] if request_bodies else b"",
                end=len(request_bodies) <= 1,
            )
            for chunk in request_bodies[1:]:
                await self._send_call_data(stream_id, chunk, end=False)
            if len(request_bodies) > 1:
                await self._send_call_data(stream_id, b"", end=True)

            reader = ConnectEnvelopeReader(
                method.output, _DEFAULT_CODEC, IdentityCompression(), None
            )
            while True:
                response_chunk = await outgoing.response_queue.get()
                if response_chunk is None:
                    if outgoing.error is not None:
                        raise outgoing.error from None
                    break
                try:
                    for message in reader.feed(response_chunk):
                        yield message
                except ConnectError as error:
                    raise SocketRpcError(error.code, error.message) from error
        finally:
            await self._send_abort(stream_id)
            self._outgoing.pop(stream_id, None)

    async def _send_call_open(
        self,
        stream_id: int,
        method: MethodInfo[REQ, RES],
        *,
        headers: Mapping[str, str] | None,
        timeout_ms: int | None,
        first_body: bytes,
        end: bool,
    ) -> None:
        init = socket_rpc_pb2.CallInit(
            service_name=google_string(method.service_name),
            method_name=google_string(method.name),
        )
        if timeout_ms is not None:
            init.timeout_ms.value = timeout_ms
        if headers:
            init.metadata.CopyFrom(metadata_from_headers(headers))
        chunks = self._chunks(first_body)
        request = socket_rpc_pb2.SocketRequest(
            stream_id=stream_id,
            call_init=init,
            end_of_stream=end and len(chunks) == 1,
        )
        if chunks[0]:
            request.message.CopyFrom(bytes_field(chunks[0]))
        await self._send_frame(socket_rpc_pb2.SocketFrame(request=request))
        for index, chunk in enumerate(chunks[1:], start=1):
            await self._let_other_calls_send(index)
            await self._send_call_data(stream_id, chunk, end=end and index == len(chunks) - 1)

    async def _send_call_data(self, stream_id: int, body: bytes, *, end: bool) -> None:
        chunks = self._chunks(body)
        for index, chunk in enumerate(chunks):
            await self._let_other_calls_send(index)
            request = socket_rpc_pb2.SocketRequest(
                stream_id=stream_id, end_of_stream=end and index == len(chunks) - 1
            )
            if chunk:
                request.message.CopyFrom(bytes_field(chunk))
            await self._send_frame(socket_rpc_pb2.SocketFrame(request=request))

    async def close(self) -> None:
        """Fail every open call and close the socket."""
        if self._closed:
            return
        self._closed = True
        self._close_event.set()
        await self._fail_all_open_calls(Code.CANCELED, "peer closed")
        await self._socket.close()

    async def _wait_for_outgoing(self, outgoing: _OutgoingCall, timeout_ms: int | None) -> None:
        if timeout_ms is None:
            await outgoing.done.wait()
            return
        try:
            await asyncio.wait_for(outgoing.done.wait(), timeout_ms / 1000)
        except TimeoutError:
            outgoing.error = SocketRpcError(Code.DEADLINE_EXCEEDED, "call deadline exceeded")
            outgoing.finished = True
            outgoing.done.set()
            raise outgoing.error from None

    async def _send_abort(self, stream_id: int) -> None:
        if self._closed:
            return
        request = socket_rpc_pb2.SocketRequest(stream_id=stream_id, abort=True)
        with contextlib.suppress(SocketRpcError, ConnectionError):
            await self._send_frame(socket_rpc_pb2.SocketFrame(request=request))

    async def _requests_until_close(
        self,
        requests: AsyncIterable[REQ],
        *,
        stop_when: asyncio.Event | None = None,
    ) -> AsyncIterator[REQ]:
        iterator = requests.__aiter__()

        async def _pull_next() -> REQ:
            return await iterator.__anext__()

        while not self._closed:
            next_item = asyncio.create_task(_pull_next())
            close_wait = asyncio.create_task(self._close_event.wait())
            waits: set[asyncio.Task[object]] = {next_item, close_wait}
            if stop_when is not None:
                waits.add(asyncio.create_task(stop_when.wait()))
            finished, pending = await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if close_wait in finished and self._close_event.is_set():
                next_item.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await next_item
                err = SocketRpcError(Code.CANCELED, "peer closed")
                raise err
            if stop_when is not None and stop_when.is_set():
                next_item.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await next_item
                return
            try:
                yield next_item.result()
            except StopAsyncIteration:
                return

    async def _fail_all_open_calls(self, code: Code, message: str) -> None:
        err = SocketRpcError(code, message)
        for outgoing in list(self._outgoing.values()):
            outgoing.error = err
            outgoing.finished = True
            outgoing.done.set()
            await outgoing.response_queue.put(None)
        self._outgoing.clear()
        for incoming in list(self._incoming.values()):
            if incoming.task:
                incoming.task.cancel()
            else:
                incoming.aborted = True
        self._incoming.clear()


def google_string(value: str) -> Any:
    from google.protobuf import wrappers_pb2

    return wrappers_pb2.StringValue(value=value)


def _decode_unary_response_body(body: bytes, message_class: type[RES]) -> bytes:
    if not body:
        try:
            message_class.FromString(b"")
        except Exception:
            msg = "call returned no response body"
            raise SocketRpcError(Code.INTERNAL, msg) from None
        return b""
    try:
        message_class.FromString(body)
        return body
    except Exception:
        return _unary_from_stream_body(body, message_class)


def _unary_from_stream_body(body: bytes, message_class: type[RES]) -> bytes:
    reader = ConnectEnvelopeReader(message_class, _DEFAULT_CODEC, IdentityCompression(), None)
    last: bytes | None = None
    offset = 0
    while offset < len(body):
        flags = body[offset]
        length = int.from_bytes(body[offset + 1 : offset + 5], "big")
        chunk = body[offset : offset + 5 + length]
        offset += 5 + length
        for message in reader.feed(chunk):
            last = _DEFAULT_CODEC.encode(message)
        if flags & END_STREAM_FLAG:
            break
    if last is None:
        msg = "call returned no response message"
        raise SocketRpcError(Code.INTERNAL, msg)
    return last
