"""The hypercorn host serves the same description on real sockets — a Connect call and a route."""

from __future__ import annotations

import asyncio
import urllib.request
from typing import Any

from google.protobuf.wrappers_pb2 import StringValue

from surmap.rpc.compose import Brick
from surmap.rpc.description import ServerDescription, ServiceModule
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.routes import HEALTH_PATH, health_routes
from tests.rpc.echo_service import echo_service


async def _echo(request: StringValue, ctx: Any) -> StringValue:
    return StringValue(value=f"echo:{request.value}")


async def _stream(request: StringValue, ctx: Any) -> Any:
    yield request


def _post(url: str, body: bytes) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"content-type": "application/proto"}
    )
    with urllib.request.urlopen(request, timeout=10.0) as response:
        return response.status, response.read()


def _get(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=10.0) as response:
        return response.status, response.read()


async def test_the_same_description_is_served_over_sockets() -> None:
    service = echo_service()
    bricks = [
        Brick(
            methods={
                "Unary": _echo,
                "ServerStream": _stream,
                "ClientStream": _echo,
                "Bidi": _stream,
            }
        )
    ]
    description = ServerDescription(
        services=(ServiceModule(service, lambda _c: bricks),),
        http_routes=health_routes(lambda: False),
    )
    host = HypercornHost(description, None)
    ports = await host.start()
    try:
        base = f"http://127.0.0.1:{ports.public}"
        status, body = await asyncio.to_thread(
            _post, f"{base}/{service.full_name}/Unary", StringValue(value="hi").SerializeToString()
        )
        health = await asyncio.to_thread(_get, f"{base}{HEALTH_PATH}")
    finally:
        await host.stop()

    assert status == 200
    assert StringValue.FromString(body) == StringValue(value="echo:hi")
    assert health == (200, b"Alive")


async def test_routes_move_to_the_management_port_when_one_is_given() -> None:
    description = ServerDescription(http_routes=health_routes(lambda: False))
    host = HypercornHost(description, None, management_port=0)
    ports = await host.start()
    try:
        assert ports.management is not None
        health = await asyncio.to_thread(_get, f"http://127.0.0.1:{ports.management}{HEALTH_PATH}")
    finally:
        await host.stop()
    assert health == (200, b"Alive")
