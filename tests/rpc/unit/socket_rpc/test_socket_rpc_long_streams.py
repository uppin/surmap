"""A long bidi stream over `SocketRpcPeer` keeps bounded memory on the serving side.

A survey stream runs for the whole survey and its replies carry point clouds, so the serving
peer must forward each reply and forget it, not hold every reply until the call ends.
"""

from __future__ import annotations

import asyncio
import tracemalloc
from collections.abc import AsyncIterator, Mapping
from typing import Any

from connectrpc.compat import google_protobuf_codecs
from connectrpc.method import IdempotencyLevel, MethodInfo
from connectrpc.request import RequestContext
from connectrpc.server import ConnectASGIApplication, Endpoint
from google.protobuf.wrappers_pb2 import BytesValue

from surmap.rpc.socket_rpc import PeerRole, SocketRpcPeer

SERVICE = "surmap.transport.v1.test.Big"
REPLY_BYTES = 256 * 1024
REPLIES = 400  # 100 MiB through one call

BIG_BIDI: MethodInfo[BytesValue, BytesValue] = MethodInfo(
    name="Bidi",
    service_name=SERVICE,
    input=BytesValue,
    output=BytesValue,
    idempotency_level=IdempotencyLevel.UNKNOWN,
)


class _BigReplies:
    async def bidi(
        self, requests: AsyncIterator[BytesValue], ctx: RequestContext[Any, Any]
    ) -> AsyncIterator[BytesValue]:
        async for _request in requests:
            for _ in range(REPLIES):
                yield BytesValue(value=b"x" * REPLY_BYTES)


class _BigApplication(ConnectASGIApplication[_BigReplies]):
    def __init__(self) -> None:
        super().__init__(
            service=_BigReplies(),
            endpoints=lambda service: {
                f"/{SERVICE}/Bidi": Endpoint.bidi_stream(BIG_BIDI, service.bidi)
            },
            codecs=google_protobuf_codecs(),
        )

    @property
    def path(self) -> str:
        return f"/{SERVICE}"


class _QueueSocket:
    def __init__(self, inbound: asyncio.Queue[bytes | None], outbound: asyncio.Queue[bytes | None]):
        self._inbound = inbound
        self._outbound = outbound

    async def send(self, frame: bytes) -> None:
        await self._outbound.put(frame)

    async def recv(self) -> bytes:
        frame = await self._inbound.get()
        if frame is None:
            raise ConnectionError("socket closed")
        return frame

    async def close(self) -> None:
        await self._outbound.put(None)


async def _one_request() -> AsyncIterator[BytesValue]:
    yield BytesValue(value=b"go")


async def test_a_long_bidi_stream_does_not_hold_its_replies_until_the_call_ends() -> None:
    # Given a serving peer whose bidi method answers one request with 100 MiB of replies, over
    # a socket that holds a few frames in flight, as a real one does
    a_to_b: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=8)
    b_to_a: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=8)
    applications: Mapping[str, ConnectASGIApplication[Any]] = {SERVICE: _BigApplication()}
    dialer = SocketRpcPeer(_QueueSocket(b_to_a, a_to_b), role=PeerRole.DIALER)
    acceptor = SocketRpcPeer(
        _QueueSocket(a_to_b, b_to_a), role=PeerRole.ACCEPTOR, applications=applications
    )
    serving = [asyncio.create_task(dialer.serve()), asyncio.create_task(acceptor.serve())]

    # When the caller reads every reply as it arrives, discarding it
    tracemalloc.start()
    try:
        received = 0
        async for reply in dialer.call_bidi_stream(BIG_BIDI, _one_request()):
            received += len(reply.value)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        await dialer.close()
        await acceptor.close()
        for task in serving:
            task.cancel()

    # Then all 100 MiB went through while the process never held more than a fraction of it
    assert received == REPLIES * REPLY_BYTES
    assert peak < 32 * 1024 * 1024, f"peak {peak / 2**20:.0f} MiB"
