"""The station's side of the fleet link: one `FleetController` per scenario, gatekeeping and
sending the commands the agent gives, and the `FleetRegistry` that links pages to them.

`FleetController.send(command)` runs in this order:

1. **Validate** — the drone is the scenario's; a route or detour has waypoints, each within
   ±`BOUND_M` east/north and `MIN_UP_M`–`MAX_UP_M` up; a given speed is within
   `MIN_SPEED_M_S`–`MAX_SPEED_M_S`; the drone's phase in the last telemetry (`docked` before
   any) allows the command, as the renderer's `FleetLog::push` would. Failing raises
   `FleetInvalid(rule)` and nothing is sent.
2. **No link** raises `FleetUnavailable("no simulation connected for scenario <id>")`.
3. **Send and wait** up to `FleetTiming.ack_timeout_s` for the page's answer to that request:
   `applied` is logged and returned, `refused` raises `FleetRefused(reason)`, silence raises
   `FleetTimeout`.

Requests are numbered from 1 per controller and serialised: the next is sent only once the
previous one is answered (or timed out), so the order sent is the order applied.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from surmap.simulation.fleet.commands import FleetCommand, Stamped
from surmap.simulation.fleet.link import Applied, DroneTelemetry, SimHello, SimMessage
from surmap.simulation.fleet.log_store import FleetLogStore
from surmap.simulation.fleet_nests import Nest
from surmap.simulation.scenario_store import ScenarioStore

__all__ = [
    "ACK_TIMEOUT_S",
    "FleetController",
    "FleetError",
    "FleetInvalid",
    "FleetRefused",
    "FleetRegistry",
    "FleetTimeout",
    "FleetTiming",
    "FleetUnavailable",
    "InvalidRule",
    "SimLink",
    "SimSocket",
]

# How long a sent command waits for the page's `applied` / `refused`, s.
ACK_TIMEOUT_S = 5.0


class InvalidRule(StrEnum):
    """Why the station refused a command before sending it (the renderer's `RefusalReason`,
    plus the scene bounds the station alone checks)."""

    UNKNOWN_DRONE = "unknown_drone"
    NO_WAYPOINTS = "no_waypoints"
    SPEED_OUT_OF_RANGE = "speed_out_of_range"
    HEIGHT_OUT_OF_RANGE = "height_out_of_range"
    OUT_OF_BOUNDS = "out_of_bounds"
    NOT_DOCKED = "not_docked"
    """`launch` while the drone is not `docked`."""
    NOT_FLYING = "not_flying"
    """`set_route` / `detour` while the drone is `docked` or `landing`."""
    ALREADY_DOCKED = "already_docked"
    """`recall` while the drone is `docked`."""


class FleetError(Exception):
    """A fleet command that did not apply."""


class FleetInvalid(FleetError):
    """The station refused the command without sending it."""

    def __init__(self, rule: InvalidRule, message: str) -> None:
        super().__init__(message)
        self.rule = rule


class FleetUnavailable(FleetError):
    """No simulation page is linked for the scenario."""


class FleetRefused(FleetError):
    """The simulation refused the command; `reason` is the page's own words."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class FleetTimeout(FleetError):
    """The linked page did not answer in time."""


Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class FleetTiming:
    """How long a command waits for its answer, and the clock that waits (injected in tests)."""

    ack_timeout_s: float = ACK_TIMEOUT_S
    sleep: Sleep = field(default=asyncio.sleep)


class SimLink(Protocol):
    """Where a controller sends its frames: the linked page."""

    async def send_text(self, text: str) -> None: ...


class SimSocket(SimLink, Protocol):
    """A page's WebSocket as the registry pumps it."""

    async def receive_text(self) -> str | None:
        """The next text frame; `None` once the page has closed."""
        ...

    async def close(self, code: int) -> None: ...


class FleetController:
    """One scenario's fleet, as the station commands it."""

    def __init__(
        self,
        scenario_id: str,
        nests: Sequence[Nest],
        log_store: FleetLogStore,
        *,
        timing: FleetTiming | None = None,
    ) -> None:
        self._scenario_id = scenario_id
        self._nests = tuple(nests)
        self._log_store = log_store
        self._timing = timing if timing is not None else FleetTiming()

    @property
    def scenario_id(self) -> str:
        return self._scenario_id

    @property
    def linked(self) -> bool:
        """Whether a page is attached."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    @property
    def session_id(self) -> int | None:
        """The current (or last) linked session, `None` before any."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    async def send(self, command: FleetCommand) -> Applied:
        """Validates, sends and waits for `command` (see the module docstring)."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def drones(self) -> tuple[DroneTelemetry, ...]:
        """Every drone as the last telemetry reported it; empty before any."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def active(self) -> str | None:
        """The drone whose eyes the page shows, per the last telemetry."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def session_log(self) -> tuple[Stamped, ...]:
        """The commands applied in the current (or last) session, in order."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def attach(self, link: SimLink, hello: SimHello) -> None:
        """Links the page that said `hello`, starting a new logged session."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def receive(self, message: SimMessage) -> None:
        """A frame from the linked page: an answer settles its request, telemetry replaces the
        last."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def detach(self) -> None:
        """Unlinks the page; a waiting request fails with `FleetUnavailable`."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")


class FleetRegistry:
    """The server's controllers, one per scenario, built from the scenario's latest manifest on
    first use, and their sessions' log store in the scenario store's file."""

    def __init__(self, store: ScenarioStore, *, timing: FleetTiming | None = None) -> None:
        self._store = store
        self._timing = timing if timing is not None else FleetTiming()
        self.log_store = FleetLogStore(store.db_path)

    def controller(self, scenario_id: str) -> FleetController:
        """The scenario's controller (the same one on every call)."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    async def link(self, scenario_id: str, socket: SimSocket) -> None:
        """Runs one page's link until it closes: the first frame must be a `fleet/v1` `hello`
        (else close `CLOSE_PROTOCOL_ERROR`); a scenario already linked closes the newcomer with
        `CLOSE_ALREADY_LINKED`; every later frame goes to the controller (an undecodable one
        closes `CLOSE_PROTOCOL_ERROR`); the close detaches it."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")
