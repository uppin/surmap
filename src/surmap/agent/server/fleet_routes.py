"""`/sim/fleet?scenario=<id>` on the agent server: the WebSocket a simulation page opened with
`?fleet=1` links through, speaking `fleet/v1` (`surmap.simulation.fleet.link`).

The route accepts the upgrade, reads `?scenario=` (a missing one closes `CLOSE_PROTOCOL_ERROR`),
and hands the socket to `SimulationRig.fleet.link`, which runs the session until the page closes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any
from urllib.parse import parse_qs

from surmap.agent.server.sim_routes import SimulationRig
from surmap.rpc.description import WebSocketRoute
from surmap.simulation.fleet.link import CLOSE_PROTOCOL_ERROR
from surmap.simulation.fleet.registry import FleetRegistry

__all__ = ["FLEET_PATH", "fleet_websocket_route", "serve_fleet_link"]

FLEET_PATH = "/sim/fleet"

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class _AsgiSocket:
    """An accepted ASGI WebSocket as the registry pumps it."""

    def __init__(self, receive: Receive, send: Send) -> None:
        self._receive = receive
        self._send = send

    async def receive_text(self) -> str | None:
        while True:
            message = await self._receive()
            if message["type"] == "websocket.disconnect":
                return None
            if message["type"] != "websocket.receive":
                continue
            text: str | None = message.get("text")
            if text is not None:
                return text
            data: bytes | None = message.get("bytes")
            if data is not None:
                # `fleet/v1` is text frames; a binary one fails to decode and closes the link.
                return data.decode(errors="replace")

    async def send_text(self, text: str) -> None:
        await self._send({"type": "websocket.send", "text": text})

    async def close(self, code: int) -> None:
        await self._send({"type": "websocket.close", "code": code})


async def serve_fleet_link(
    registry: FleetRegistry, scope: dict[str, Any], receive: Receive, send: Send
) -> None:
    """The ASGI WebSocket app behind `FLEET_PATH`: one page's link, until it closes."""
    if (await receive())["type"] != "websocket.connect":
        return
    await send({"type": "websocket.accept"})
    socket = _AsgiSocket(receive, send)
    scenario = parse_qs(scope.get("query_string", b"").decode()).get("scenario")
    if not scenario or not scenario[0]:
        await socket.close(CLOSE_PROTOCOL_ERROR)
        return
    await registry.link(scenario[0], socket)


def fleet_websocket_route(rig: SimulationRig) -> WebSocketRoute[None]:
    """`FLEET_PATH`, linking pages to `rig.fleet`."""
    return WebSocketRoute(FLEET_PATH, lambda _context: partial(serve_fleet_link, rig.fleet))
