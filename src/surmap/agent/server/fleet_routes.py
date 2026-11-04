"""`/sim/fleet?scenario=<id>` on the agent server: the WebSocket a simulation page opened with
`?fleet=1` links through, speaking `fleet/v1` (`surmap.simulation.fleet.link`).

The route accepts the upgrade, reads `?scenario=` (a missing one closes `CLOSE_PROTOCOL_ERROR`),
and hands the socket to `SimulationRig.fleet.link`, which runs the session until the page closes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from surmap.agent.server.sim_routes import SimulationRig
from surmap.rpc.description import WebSocketRoute
from surmap.simulation.fleet.controller import FleetRegistry

__all__ = ["FLEET_PATH", "fleet_websocket_route", "serve_fleet_link"]

FLEET_PATH = "/sim/fleet"

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


async def serve_fleet_link(
    registry: FleetRegistry, scope: dict[str, Any], receive: Receive, send: Send
) -> None:
    """The ASGI WebSocket app behind `FLEET_PATH`: one page's link, until it closes."""
    # TODO(pr-3): implement
    raise NotImplementedError("pr-3: implement")


def fleet_websocket_route(rig: SimulationRig) -> WebSocketRoute[None]:
    """`FLEET_PATH`, linking pages to `rig.fleet`."""
    return WebSocketRoute(FLEET_PATH, lambda _context: partial(serve_fleet_link, rig.fleet))
