"""ConnectRPC over one WebSocket, both directions — `SocketRpcPeer` conformance (#connect-unify n5).

Two peers share an in-memory socket pair. One serves a test echo service — declared with
`MethodInfo` over `google.protobuf.StringValue`, one method of each kind — and the other calls
it; then the roles swap, because the compute channel needs the peer that *accepted* the socket
to call the peer that dialed it.

These live in the server package because its environment has connect-python; the transport
itself lives in the calling peer, which gains connect-python with this node's
green (after approval).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest
from connectrpc.code import Code
from connectrpc.compat import google_protobuf_codecs
from connectrpc.errors import ConnectError
from connectrpc.method import IdempotencyLevel, MethodInfo
from connectrpc.request import RequestContext
from connectrpc.server import ConnectASGIApplication, Endpoint
from google.protobuf.wrappers_pb2 import StringValue

from surmap.rpc.socket_rpc import (
    PeerRole,
    SocketRpcError,
    SocketRpcPeer,
)

ECHO_SERVICE = "surmap.transport.v1.test.Echo"


def _method(name: str) -> MethodInfo[StringValue, StringValue]:
    return MethodInfo(
        name=name,
        service_name=ECHO_SERVICE,
        input=StringValue,
        output=StringValue,
        idempotency_level=IdempotencyLevel.UNKNOWN,
    )


UNARY = _method("Unary")
SERVER_STREAM = _method("ServerStream")
CLIENT_STREAM = _method("ClientStream")
BIDI = _method("Bidi")
FAIL = _method("Fail")
HEADER = _method("Header")
NO_SUCH_METHOD = _method("NoSuchMethod")


class _EchoService:
    async def unary(self, request: StringValue, ctx: RequestContext[Any, Any]) -> StringValue:
        return StringValue(value=f"echo:{request.value}")

    async def server_stream(
        self, request: StringValue, ctx: RequestContext[Any, Any]
    ) -> AsyncIterator[StringValue]:
        for index in range(3):
            yield StringValue(value=f"{request.value}:{index}")

    async def client_stream(
        self, requests: AsyncIterator[StringValue], ctx: RequestContext[Any, Any]
    ) -> StringValue:
        return StringValue(value="+".join([request.value async for request in requests]))

    async def bidi(
        self, requests: AsyncIterator[StringValue], ctx: RequestContext[Any, Any]
    ) -> AsyncIterator[StringValue]:
        async for request in requests:
            yield StringValue(value=f"echo:{request.value}")

    async def fail(self, request: StringValue, ctx: RequestContext[Any, Any]) -> StringValue:
        raise ConnectError(Code.FAILED_PRECONDITION, f"refused {request.value}")

    async def header(self, request: StringValue, ctx: RequestContext[Any, Any]) -> StringValue:
        return StringValue(value=ctx.request_headers.get(request.value) or "")


class _EchoApplication(ConnectASGIApplication[_EchoService]):
    def __init__(self) -> None:
        super().__init__(
            service=_EchoService(),
            endpoints=lambda service: {
                f"/{ECHO_SERVICE}/Unary": Endpoint.unary(UNARY, service.unary),
                f"/{ECHO_SERVICE}/ServerStream": Endpoint.server_stream(
                    SERVER_STREAM, service.server_stream
                ),
                f"/{ECHO_SERVICE}/ClientStream": Endpoint.client_stream(
                    CLIENT_STREAM, service.client_stream
                ),
                f"/{ECHO_SERVICE}/Bidi": Endpoint.bidi_stream(BIDI, service.bidi),
                f"/{ECHO_SERVICE}/Fail": Endpoint.unary(FAIL, service.fail),
                f"/{ECHO_SERVICE}/Header": Endpoint.unary(HEADER, service.header),
            },
            codecs=google_protobuf_codecs(),
        )

    @property
    def path(self) -> str:
        return f"/{ECHO_SERVICE}"


class _QueueSocket:
    """One end of an in-memory socket pair."""

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


def _socket_pair() -> tuple[_QueueSocket, _QueueSocket]:
    a_to_b: asyncio.Queue[bytes | None] = asyncio.Queue()
    b_to_a: asyncio.Queue[bytes | None] = asyncio.Queue()
    return _QueueSocket(b_to_a, a_to_b), _QueueSocket(a_to_b, b_to_a)


def _echo_applications() -> Mapping[str, ConnectASGIApplication[Any]]:
    return {ECHO_SERVICE: _EchoApplication()}


@pytest.fixture
async def peers() -> AsyncIterator[tuple[SocketRpcPeer, SocketRpcPeer]]:
    """(dialer, acceptor) — both serve the echo service, both can call it on the other."""
    dialer_socket, acceptor_socket = _socket_pair()
    dialer = SocketRpcPeer(dialer_socket, role=PeerRole.DIALER, applications=_echo_applications())
    acceptor = SocketRpcPeer(
        acceptor_socket, role=PeerRole.ACCEPTOR, applications=_echo_applications()
    )
    serving = [asyncio.create_task(dialer.serve()), asyncio.create_task(acceptor.serve())]
    yield dialer, acceptor
    await dialer.close()
    await acceptor.close()
    for task in serving:
        task.cancel()


async def _values(messages: AsyncIterator[StringValue]) -> list[str]:
    return [message.value async for message in messages]


async def _requests(*values: str) -> AsyncIterator[StringValue]:
    for value in values:
        yield StringValue(value=value)


def test_the_dialer_opens_odd_stream_ids_and_the_acceptor_even_ones() -> None:
    dialer_socket, acceptor_socket = _socket_pair()
    dialer = SocketRpcPeer(dialer_socket, role=PeerRole.DIALER)
    acceptor = SocketRpcPeer(acceptor_socket, role=PeerRole.ACCEPTOR)

    assert [dialer.next_stream_id() for _ in range(3)] == [1, 3, 5]
    assert [acceptor.next_stream_id() for _ in range(3)] == [2, 4, 6]


async def test_a_unary_call_from_the_dialer_is_answered_by_the_acceptor(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    dialer, _acceptor = peers
    response = await dialer.call_unary(UNARY, StringValue(value="hi"))
    assert response.value == "echo:hi"


async def test_a_unary_call_from_the_acceptor_is_answered_by_the_dialer(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    _dialer, acceptor = peers
    response = await acceptor.call_unary(UNARY, StringValue(value="assign"))
    assert response.value == "echo:assign"


async def test_calls_in_both_directions_share_one_socket_concurrently(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    dialer, acceptor = peers
    outbound, inbound = await asyncio.gather(
        dialer.call_unary(UNARY, StringValue(value="up")),
        acceptor.call_unary(UNARY, StringValue(value="down")),
    )
    assert (outbound.value, inbound.value) == ("echo:up", "echo:down")


async def test_a_server_stream_delivers_every_message_in_order(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    _dialer, acceptor = peers
    values = await _values(acceptor.call_server_stream(SERVER_STREAM, StringValue(value="s")))
    assert values == ["s:0", "s:1", "s:2"]


async def test_a_client_stream_collects_every_request(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    dialer, _acceptor = peers
    response = await dialer.call_client_stream(CLIENT_STREAM, _requests("a", "b", "c"))
    assert response.value == "a+b+c"


async def test_a_bidi_stream_echoes_every_request_in_order(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    _dialer, acceptor = peers
    values = await _values(acceptor.call_bidi_stream(BIDI, _requests("x", "y")))
    assert values == ["echo:x", "echo:y"]


async def test_a_handler_error_reaches_the_caller_with_its_connect_code(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    dialer, _acceptor = peers
    with pytest.raises(SocketRpcError) as error:
        await dialer.call_unary(FAIL, StringValue(value="job-1"))
    assert error.value.code == Code.FAILED_PRECONDITION
    assert "refused job-1" in error.value.message


async def test_an_unknown_method_answers_unimplemented(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    _dialer, acceptor = peers
    with pytest.raises(SocketRpcError) as error:
        await acceptor.call_unary(NO_SUCH_METHOD, StringValue(value="?"))
    assert error.value.code == Code.UNIMPLEMENTED


async def test_request_metadata_reaches_the_handler_as_request_headers(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    _dialer, acceptor = peers
    response = await acceptor.call_unary(
        HEADER,
        StringValue(value="surmap-probe"),
        headers={"surmap-probe": "carried"},
    )
    assert response.value == "carried"


async def test_closing_a_peer_fails_its_open_calls(
    peers: tuple[SocketRpcPeer, SocketRpcPeer],
) -> None:
    dialer, _acceptor = peers

    async def _never_ending() -> AsyncIterator[StringValue]:
        yield StringValue(value="first")
        await asyncio.Event().wait()

    call = asyncio.create_task(dialer.call_client_stream(CLIENT_STREAM, _never_ending()))
    await dialer.close()
    with pytest.raises(SocketRpcError) as error:
        await call
    assert error.value.code in {Code.CANCELED, Code.UNAVAILABLE}
