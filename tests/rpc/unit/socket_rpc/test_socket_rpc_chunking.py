"""A body larger than one frame crosses the socket as several (#socket-chunking).

The reproduction of the incident is a socket that refuses any frame above a limit, which is what
`websockets` does with `max_size`: the receiver closes the channel (1009) and every open call fails.
The peers must therefore never write a frame above the limit, whatever the body size.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
from connectrpc.code import Code
from google.protobuf.wrappers_pb2 import StringValue

from surmap.rpc.socket_rpc import PeerRole, SocketRpcError, SocketRpcPeer
from surmap.rpc.socket_rpc._wire import decode_frame, message_bytes
from tests.rpc.unit.socket_rpc.test_socket_rpc import (
    BIDI,
    CLIENT_STREAM,
    SERVER_STREAM,
    UNARY,
    _echo_applications,
    _QueueSocket,
    _socket_pair,
)

ONE_MIB = 1024 * 1024
LARGE = "x" * (5 * ONE_MIB // 2)


@dataclass(frozen=True)
class _Frame:
    stream_id: int
    payload_bytes: int
    opens_call: bool
    ends_stream: bool
    is_request: bool


class _WireSocket:
    """One end of a socket pair that refuses frames above `limit`, records what it was given,
    and never suspends in `send`, like the gRPC transport's unbounded queue."""

    def __init__(self, inner: _QueueSocket, limit: int, wire: list[_Frame]) -> None:
        self._inner = inner
        self._limit = limit
        self._wire = wire

    async def send(self, frame: bytes) -> None:
        if len(frame) > self._limit:
            await self._inner.close()
            raise ConnectionError(f"frame of {len(frame)} bytes exceeds limit of {self._limit}")
        self._wire.append(_describe(frame))
        await self._inner.send(frame)

    async def recv(self) -> bytes:
        return await self._inner.recv()

    async def close(self) -> None:
        await self._inner.close()


def _describe(raw: bytes) -> _Frame:
    frame = decode_frame(raw)
    if frame.WhichOneof("kind") == "request":
        request = frame.request
        return _Frame(
            request.stream_id,
            len(message_bytes(request.message)),
            request.HasField("call_init"),
            request.end_of_stream,
            is_request=True,
        )
    response = frame.response
    return _Frame(
        response.stream_id,
        len(message_bytes(response.message)),
        False,
        response.end_of_stream,
        is_request=False,
    )


@asynccontextmanager
async def _peers_over_limited_socket(
    *, limit: int = ONE_MIB, **options: int
) -> AsyncIterator[tuple[SocketRpcPeer, SocketRpcPeer, list[_Frame]]]:
    wire: list[_Frame] = []
    dialer_end, acceptor_end = _socket_pair()
    dialer = SocketRpcPeer(
        _WireSocket(dialer_end, limit, wire),
        role=PeerRole.DIALER,
        applications=_echo_applications(),
        **options,
    )
    acceptor = SocketRpcPeer(
        _WireSocket(acceptor_end, limit, wire),
        role=PeerRole.ACCEPTOR,
        applications=_echo_applications(),
        **options,
    )
    serving = [asyncio.create_task(dialer.serve()), asyncio.create_task(acceptor.serve())]
    try:
        yield dialer, acceptor, wire
    finally:
        await dialer.close()
        await acceptor.close()
        for task in serving:
            task.cancel()


async def _requests(*values: str) -> AsyncIterator[StringValue]:
    for value in values:
        yield StringValue(value=value)


async def test_a_unary_body_larger_than_the_frame_limit_round_trips() -> None:
    async with _peers_over_limited_socket() as (dialer, _acceptor, _wire):
        response = await dialer.call_unary(UNARY, StringValue(value=LARGE))

    assert response.value == f"echo:{LARGE}"


async def test_a_server_stream_message_larger_than_the_frame_limit_round_trips() -> None:
    async with _peers_over_limited_socket() as (_dialer, acceptor, _wire):
        values = [
            message.value
            async for message in acceptor.call_server_stream(
                SERVER_STREAM, StringValue(value=LARGE)
            )
        ]

    assert values == [f"{LARGE}:0", f"{LARGE}:1", f"{LARGE}:2"]


async def test_a_client_stream_message_larger_than_the_frame_limit_round_trips() -> None:
    async with _peers_over_limited_socket() as (dialer, _acceptor, _wire):
        response = await dialer.call_client_stream(CLIENT_STREAM, _requests("a", LARGE, "b"))

    assert response.value == f"a+{LARGE}+b"


async def test_a_bidi_message_larger_than_the_frame_limit_round_trips() -> None:
    async with _peers_over_limited_socket() as (dialer, _acceptor, _wire), asyncio.timeout(10):
        echoed = [
            message.value async for message in dialer.call_bidi_stream(BIDI, _requests("a", LARGE))
        ]

    assert echoed == ["echo:a", f"echo:{LARGE}"]


async def test_no_frame_carries_more_than_the_chunk_size_in_either_direction() -> None:
    chunk_size = 1024
    async with _peers_over_limited_socket(chunk_size=chunk_size) as (dialer, _acceptor, wire):
        await dialer.call_unary(UNARY, StringValue(value="y" * (10 * chunk_size)))

    assert max(frame.payload_bytes for frame in wire) <= chunk_size
    assert {frame.payload_bytes > 0 for frame in wire if frame.opens_call} == {True}


async def test_only_the_last_frame_of_a_body_ends_the_stream() -> None:
    chunk_size = 1024
    async with _peers_over_limited_socket(chunk_size=chunk_size) as (dialer, _acceptor, wire):
        await dialer.call_unary(UNARY, StringValue(value="y" * (10 * chunk_size)))

    request_frames = [
        frame for frame in wire if frame.is_request and frame.stream_id == 1 and frame.payload_bytes
    ]
    assert [frame.ends_stream for frame in request_frames].count(True) == 1
    assert request_frames[-1].ends_stream


async def test_a_small_call_is_not_held_up_behind_a_large_one() -> None:
    chunk_size = 1024
    async with _peers_over_limited_socket(chunk_size=chunk_size) as (dialer, _acceptor, wire):
        large = asyncio.create_task(dialer.call_unary(UNARY, StringValue(value="z" * ONE_MIB)))
        for _ in range(3):
            await asyncio.sleep(0)
        small = await dialer.call_unary(UNARY, StringValue(value="hi"))
        await large

    large_stream, small_stream = 1, 3
    small_opened_at = next(
        index
        for index, frame in enumerate(wire)
        if frame.stream_id == small_stream and frame.opens_call
    )
    large_ended_at = next(
        index
        for index, frame in enumerate(wire)
        if frame.stream_id == large_stream and frame.ends_stream and index < len(wire)
    )
    assert small.value == "echo:hi"
    assert small_opened_at < large_ended_at


async def test_a_body_over_the_per_call_cap_fails_that_call_and_leaves_the_channel_up() -> None:
    async with _peers_over_limited_socket(chunk_size=16 * 1024, max_call_bytes=64 * 1024) as (
        dialer,
        _acceptor,
        _wire,
    ):
        with pytest.raises(SocketRpcError) as refused:
            await dialer.call_unary(UNARY, StringValue(value="w" * (200 * 1024)))
        later = await dialer.call_unary(UNARY, StringValue(value="still here"))

    assert refused.value.code == Code.RESOURCE_EXHAUSTED
    assert later.value == "echo:still here"
