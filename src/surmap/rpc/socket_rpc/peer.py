"""One end of a Connect-over-WebSocket socket: it serves, and it calls."""

from __future__ import annotations

import asyncio
import contextvars
import time
from collections.abc import Mapping
from typing import Any

from connectrpc._protocol import ConnectWireError
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.server import ConnectASGIApplication

from surmap.rpc.socket_rpc._asgi import (
    CONNECT_PROTOCOL_VERSION,
    END_STREAM_FLAG,
    _connect_error_from_collected,
    endpoint_kind,
    invoke_application,
    unary_content_type,
    unary_response_body,
)
from surmap.rpc.socket_rpc._calls import _Caller
from surmap.rpc.socket_rpc._trace import register_peer, socket_debug, socket_trace
from surmap.rpc.socket_rpc._types import (
    _DEFAULT_CODEC,
    DEFAULT_CHUNK_BYTES,
    DEFAULT_MAX_CALL_BYTES,
    FrameSocket,
    OpenCall,
    PeerRole,
    SocketRpcError,
    _IncomingCall,
    _OutgoingCall,
)
from surmap.rpc.socket_rpc._wire import (
    bytes_field,
    decode_frame,
    error_from_socket,
    headers_from_metadata,
    message_bytes,
    socket_error,
)
from surmap.transport.v1 import socket_rpc_pb2

__all__ = ["FrameSocket", "PeerRole", "SocketRpcError", "SocketRpcPeer"]

_unary_request_body: contextvars.ContextVar[bytes | None] = contextvars.ContextVar(
    "socket_rpc_unary_request_body", default=None
)


def unary_request_body_for_verify() -> bytes | None:
    """Wire body for the unary call currently being dispatched, if any."""
    return _unary_request_body.get()


class SocketRpcPeer(_Caller):
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
        register_peer(self)

    @property
    def role_name(self) -> str:
        return self._role.value

    def open_calls(self) -> list[OpenCall]:
        """The calls this peer has open now, incoming and outgoing, oldest first."""
        now = time.monotonic()
        calls = [
            OpenCall("in", call.stream_id, call.method_path, now - call.started)
            for call in self._incoming.values()
        ] + [
            OpenCall("out", call.stream_id, call.method_path, now - call.started)
            for call in self._outgoing.values()
        ]
        return sorted(calls, key=lambda call: -call.age_s)

    @property
    def role(self) -> PeerRole:
        return self._role

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
            socket_trace(
                "socket_rpc.serve.exit",
                role=self._role.value,
                open_calls=[f"{c.direction}:{c.method}" for c in self.open_calls()],
            )
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
            socket_trace(
                "call.in.open",
                role=self._role.value,
                stream_id=stream_id,
                method=incoming.method_path,
            )
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
                # Forget what was sent, so a long stream holds at most one partial message.
                del stream_buffer[:stream_offset]
                stream_offset = 0

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
            socket_trace(
                "call.in.end",
                role=self._role.value,
                stream_id=incoming.stream_id,
                method=incoming.method_path,
                duration_s=round(time.monotonic() - incoming.started, 3),
            )

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

    async def close(self) -> None:
        """Fail every open call and close the socket."""
        if self._closed:
            return
        self._closed = True
        self._close_event.set()
        await self._fail_all_open_calls(Code.CANCELED, "peer closed")
        await self._socket.close()

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
