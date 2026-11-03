"""The calling half of a `SocketRpcPeer`: calls it starts on the other end, and the frames
both halves send."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from typing import Any, cast

from connectrpc._compression import IdentityCompression
from connectrpc._protocol_connect import ConnectEnvelopeReader, ConnectEnvelopeWriter
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.method import MethodInfo
from connectrpc.server import ConnectASGIApplication

from surmap.rpc.socket_rpc._asgi import END_STREAM_FLAG, endpoint_kind
from surmap.rpc.socket_rpc._trace import socket_trace
from surmap.rpc.socket_rpc._types import (
    _DEFAULT_CODEC,
    REQ,
    RES,
    FrameSocket,
    SocketRpcError,
    _OutgoingCall,
)
from surmap.rpc.socket_rpc._wire import (
    bytes_field,
    encode_frame,
    metadata_from_headers,
)
from surmap.transport.v1 import socket_rpc_pb2


class _Caller:
    """Starts calls on the peer at the other end of the socket. `SocketRpcPeer` sets the state
    below in its `__init__`."""

    _socket: FrameSocket
    _send_lock: asyncio.Lock
    _closed: bool
    _close_event: asyncio.Event
    _chunk_size: int
    _next_id: int
    _id_step: int
    _applications: dict[str, ConnectASGIApplication[Any]]
    _outgoing: dict[int, _OutgoingCall]

    def _open_outgoing(self, outgoing: _OutgoingCall) -> None:
        self._outgoing[outgoing.stream_id] = outgoing
        socket_trace(
            "call.out.open",
            stream_id=outgoing.stream_id,
            method=outgoing.method_path,
            kind=outgoing.kind,
        )

    def _end_outgoing(self, stream_id: int) -> None:
        outgoing = self._outgoing.pop(stream_id, None)
        if outgoing is None:
            return
        socket_trace(
            "call.out.end",
            stream_id=stream_id,
            method=outgoing.method_path,
            duration_s=round(time.monotonic() - outgoing.started, 3),
            error=outgoing.error.code.name if outgoing.error is not None else None,
        )

    def next_stream_id(self) -> int:
        """Reserve the id of the next call this peer starts."""
        stream_id = self._next_id
        self._next_id += self._id_step
        return stream_id

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
        self._open_outgoing(outgoing)
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
            self._end_outgoing(stream_id)

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
            self._open_outgoing(outgoing)
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
                self._end_outgoing(stream_id)

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
        self._open_outgoing(outgoing)
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
            self._end_outgoing(stream_id)

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
        self._open_outgoing(outgoing)
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
            self._end_outgoing(stream_id)

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
