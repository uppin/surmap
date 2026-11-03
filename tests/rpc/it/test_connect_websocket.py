"""A host serves its Connect services over one WebSocket, on real sockets.

The host mounts every composed service on `connect_websocket_path`; a client dials it with the
`websockets` library and calls through a dialer `SocketRpcPeer`. The host keeps its sockets alive,
so a proxy that drops idle connections keeps them, and a bearer token, when set, guards both
Connect over HTTP and the WebSocket upgrade — the health route stays open.
"""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import websockets
from connectrpc.method import IdempotencyLevel, MethodInfo
from google.protobuf.descriptor import ServiceDescriptor
from google.protobuf.wrappers_pb2 import StringValue

from surmap.rpc.compose import Brick
from surmap.rpc.description import ServerDescription, ServiceModule
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.routes import HEALTH_PATH, health_routes
from surmap.rpc.socket_rpc import PeerRole, SocketRpcPeer, WebSocketFrames
from tests.rpc.echo_service import echo_service

CONNECT_PATH = "/connect"
TOKEN = "survey-secret"


async def _echo(request: StringValue, ctx: Any) -> StringValue:
    return StringValue(value=f"echo:{request.value}")


async def _echo_each(requests: AsyncIterator[StringValue], ctx: Any) -> AsyncIterator[StringValue]:
    async for request in requests:
        yield StringValue(value=f"echo:{request.value}")


async def _first(request: StringValue, ctx: Any) -> AsyncIterator[StringValue]:
    yield request


def _method(service: ServiceDescriptor, name: str) -> MethodInfo[StringValue, StringValue]:
    return MethodInfo(
        name=name,
        service_name=service.full_name,
        input=StringValue,
        output=StringValue,
        idempotency_level=IdempotencyLevel.UNKNOWN,
    )


def _echo_description(service: ServiceDescriptor) -> ServerDescription[None]:
    bricks = [
        Brick(
            methods={
                "Unary": _echo,
                "ServerStream": _first,
                "ClientStream": _echo,
                "Bidi": _echo_each,
            }
        )
    ]
    return ServerDescription(
        services=(ServiceModule(service, lambda _c: bricks),),
        http_routes=health_routes(lambda: False),
        connect_websocket_path=CONNECT_PATH,
    )


@asynccontextmanager
async def _serving(service: ServiceDescriptor, **host_options: Any) -> AsyncIterator[int]:
    host = HypercornHost(_echo_description(service), None, **host_options)
    ports = await host.start()
    try:
        yield ports.public
    finally:
        await host.stop()


@asynccontextmanager
async def _dialed(url: str, headers: dict[str, str] | None = None) -> AsyncIterator[SocketRpcPeer]:
    async with websockets.connect(url, additional_headers=headers) as socket:
        peer = SocketRpcPeer(WebSocketFrames(socket), role=PeerRole.DIALER)
        serving = asyncio.create_task(peer.serve())
        try:
            yield peer
        finally:
            await peer.close()
            serving.cancel()


async def _requests(*values: str) -> AsyncIterator[StringValue]:
    for value in values:
        yield StringValue(value=value)


def _post_unary(url: str, headers: dict[str, str]) -> int:
    request = urllib.request.Request(
        url,
        data=StringValue(value="hi").SerializeToString(),
        method="POST",
        headers={"content-type": "application/proto", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def _get_status(url: str) -> int:
    with urllib.request.urlopen(url, timeout=10.0) as response:
        return int(response.status)


async def test_a_unary_call_over_the_websocket_reaches_the_composed_service() -> None:
    # Given a host serving the echo service on its Connect WebSocket path
    service = echo_service()
    async with _serving(service) as port:
        # When a client dials the path and calls Unary
        async with _dialed(f"ws://127.0.0.1:{port}{CONNECT_PATH}") as peer:
            reply = await peer.call_unary(_method(service, "Unary"), StringValue(value="hi"))

    # Then the service answered it
    assert reply.value == "echo:hi"


async def test_a_bidi_call_interleaves_requests_and_replies_over_one_socket() -> None:
    # Given a host serving the echo service on its Connect WebSocket path
    service = echo_service()
    async with _serving(service) as port:
        # When a client streams three requests on Bidi over one dialed socket
        async with _dialed(f"ws://127.0.0.1:{port}{CONNECT_PATH}") as peer:
            replies = [
                reply.value
                async for reply in peer.call_bidi_stream(
                    _method(service, "Bidi"), _requests("a", "b", "c")
                )
            ]

    # Then each request came back, in order
    assert replies == ["echo:a", "echo:b", "echo:c"]


class _IdleCuttingProxy:
    """A TCP relay that drops a connection once the server sent nothing for `idle_s`."""

    def __init__(self, upstream_port: int, idle_s: float) -> None:
        self._upstream_port = upstream_port
        self._idle_s = idle_s
        self.port = 0
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._relay, "127.0.0.1", 0)
        self.port = int(self._server.sockets[0].getsockname()[1])

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _relay(self, client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter) -> None:
        upstream_r, upstream_w = await asyncio.open_connection("127.0.0.1", self._upstream_port)

        async def pump(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter, idle: bool
        ) -> None:
            while True:
                if idle:
                    chunk = await asyncio.wait_for(reader.read(65536), self._idle_s)
                else:
                    chunk = await reader.read(65536)
                if not chunk:
                    return
                writer.write(chunk)
                await writer.drain()

        tasks = [
            asyncio.create_task(pump(client_r, upstream_w, idle=False)),
            asyncio.create_task(pump(upstream_r, client_w, idle=True)),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except Exception:
            pass
        for task in tasks:
            task.cancel()
        client_w.close()
        upstream_w.close()


async def test_an_idle_socket_outlives_a_proxy_that_drops_idle_connections() -> None:
    # Given a host that keeps its sockets alive every 0.2 s, behind a proxy that drops a
    # connection once the server side was silent for 1 s
    service = echo_service()
    async with _serving(service, websocket_keepalive_s=0.2) as port:
        proxy = _IdleCuttingProxy(port, idle_s=1.0)
        await proxy.start()
        try:
            # When a dialed socket carries no call for three of the proxy's idle windows
            async with _dialed(f"ws://127.0.0.1:{proxy.port}{CONNECT_PATH}") as peer:
                await asyncio.sleep(3.0)
                reply = await peer.call_unary(_method(service, "Unary"), StringValue(value="late"))
        finally:
            await proxy.stop()

    # Then the socket was still open for the call
    assert reply.value == "echo:late"


async def test_a_websocket_without_the_token_is_told_unauthorized_and_closed() -> None:
    # Given a host guarded by a bearer token
    service = echo_service()
    async with _serving(service, auth_token=TOKEN) as port:
        # When a client dials without the token
        async with websockets.connect(f"ws://127.0.0.1:{port}{CONNECT_PATH}") as socket:
            # Then it is told "unauthorized" as data, then closed with 4401. A proxy in front may
            # rewrite an HTTP 401 on the upgrade and the close code, but passes the frame.
            told = await asyncio.wait_for(socket.recv(), 5.0)
            with pytest.raises(websockets.ConnectionClosed) as closed:
                await socket.recv()

    assert told == "unauthorized"
    assert closed.value.rcvd is not None and closed.value.rcvd.code == 4401


async def test_an_authorized_websocket_is_greeted_with_an_empty_frame() -> None:
    # Given a host guarded by a bearer token
    service = echo_service()
    async with _serving(service, auth_token=TOKEN) as port:
        # When a client dials with the token
        headers = {"Authorization": f"Bearer {TOKEN}"}
        url = f"ws://127.0.0.1:{port}{CONNECT_PATH}"
        async with websockets.connect(url, additional_headers=headers) as socket:
            # Then the first frame is empty: the socket is open for calls
            first = await asyncio.wait_for(socket.recv(), 5.0)

    assert first == b""


async def test_a_websocket_with_the_token_is_served() -> None:
    # Given a host guarded by a bearer token
    service = echo_service()
    async with _serving(service, auth_token=TOKEN) as port:
        # When a client dials with the token and calls Unary
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with _dialed(f"ws://127.0.0.1:{port}{CONNECT_PATH}", headers) as peer:
            reply = await peer.call_unary(_method(service, "Unary"), StringValue(value="hi"))

    # Then the call is served
    assert reply.value == "echo:hi"


async def test_connect_over_http_without_the_token_answers_401_and_health_stays_open() -> None:
    # Given a host guarded by a bearer token
    service = echo_service()
    async with _serving(service, auth_token=TOKEN) as port:
        base = f"http://127.0.0.1:{port}"
        # When Connect over HTTP is called without, then with, the token, and health is read
        without = await asyncio.to_thread(_post_unary, f"{base}/{service.full_name}/Unary", {})
        with_token = await asyncio.to_thread(
            _post_unary,
            f"{base}/{service.full_name}/Unary",
            {"Authorization": f"Bearer {TOKEN}"},
        )
        health = await asyncio.to_thread(_get_status, f"{base}{HEALTH_PATH}")

    # Then only the tokenless call is refused
    assert (without, with_token, health) == (401, 200, 200)
