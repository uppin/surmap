"""A fleet page streams two drones over a real bridge socket: `serve_bevy_bridge` on an ephemeral
loopback port with a `FleetPerception` per connection (fake maps and segmentation from
`tests.fleet_perception_fakes`), and a real `websockets` client sending the wire messages as the
page does when the agent switches the active drone.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

import websockets

from surmap.simulation.bevy_bridge import BridgeSession, serve_bevy_bridge
from surmap.simulation.fleet.perception import FleetPerception, PerceptionRegistry
from tests.fleet_fakes import eventually
from tests.fleet_perception_fakes import (
    NE_D1,
    SCENARIO,
    SW_D1,
    RecordingBackends,
    RecordingSinks,
    a_hello,
    blocks,
)

STEP_TIMEOUT_S = 10.0


@dataclass
class Bridge:
    """The station's stereo bridge on loopback, and what its fakes saw."""

    url: str
    registry: PerceptionRegistry
    backends: RecordingBackends

    async def a_page_streams(self, *messages: bytes) -> list[dict[str, object]]:
        """A page connects, sends `messages` in order and disconnects; the status replies."""
        replies: list[dict[str, object]] = []
        async with websockets.connect(self.url) as socket:
            for message in messages:
                await socket.send(message)
                reply = await asyncio.wait_for(socket.recv(), STEP_TIMEOUT_S)
                replies.append(json.loads(reply))
        return replies

    def every_map_is_closed(self) -> bool:
        return bool(self.backends.built) and all(b.closed for b in self.backends.built)


@asynccontextmanager
async def a_bridge() -> AsyncIterator[Bridge]:
    events: list[str] = []
    backends = RecordingBackends(events)
    registry = PerceptionRegistry()

    def a_page_connection() -> BridgeSession:
        return FleetPerception(backends, RecordingSinks(events), registry=registry)

    server = await serve_bevy_bridge("127.0.0.1", 0, a_page_connection)
    bound = next(iter(server.sockets or ()))
    port = int(cast("tuple[str, int]", bound.getsockname())[1])
    try:
        yield Bridge(f"ws://127.0.0.1:{port}", registry, backends)
    finally:
        server.close()
        await server.wait_closed()


def drone_and_frames(replies: list[dict[str, object]]) -> list[tuple[object, object]]:
    return [(reply.get("drone_id"), reply["frames"]) for reply in replies]


async def test_two_drones_streamed_over_the_bridge_each_get_their_own_map() -> None:
    # Given the station's bridge
    async with a_bridge() as bridge:
        # When a fleet page streams nest-sw-d1, then nest-ne-d1, then nest-sw-d1 again
        replies = await bridge.a_page_streams(
            a_hello(SCENARIO), *blocks((SW_D1, 2), (NE_D1, 2), (SW_D1, 1))
        )

    # Then every reply counts the frames of its own drone's map, nest-sw-d1's continuing
    assert drone_and_frames(replies) == [
        (None, 0),
        (SW_D1, 1),
        (SW_D1, 2),
        (NE_D1, 1),
        (NE_D1, 2),
        (SW_D1, 3),
    ]


async def test_disconnecting_the_page_closes_every_drone_s_map() -> None:
    # Given the station's bridge
    async with a_bridge() as bridge:
        # When a fleet page streams two drones and disconnects
        await bridge.a_page_streams(a_hello(SCENARIO), *blocks((SW_D1, 1), (NE_D1, 1)))

        # Then both drones' maps are closed, and the scenario has no streaming page any more
        await eventually(bridge.every_map_is_closed)
        assert len(bridge.backends.built) == 2
        assert bridge.registry.perception(SCENARIO) is None
