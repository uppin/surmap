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
import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from surmap.simulation.fleet.commands import (
    BOUND_M,
    MAX_SPEED_M_S,
    MAX_UP_M,
    MIN_SPEED_M_S,
    MIN_UP_M,
    Detour,
    FleetCommand,
    Launch,
    Recall,
    Route,
    SetActive,
    SetRoute,
    Stamped,
    Waypoint,
)
from surmap.simulation.fleet.link import (
    CLOSE_ALREADY_LINKED,
    CLOSE_PROTOCOL_ERROR,
    Applied,
    DroneTelemetry,
    FleetLinkError,
    Phase,
    Refused,
    SimHello,
    SimMessage,
    Telemetry,
    decode_sim_message,
    encode_command,
)
from surmap.simulation.fleet.log_store import FleetLogStore
from surmap.simulation.fleet_nests import Nest, nests_of
from surmap.simulation.scenario_store import ScenarioStore, UnknownRecord

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

# The renderer's fixed integration step, s, and the float slack when it turns a time into a step
# number: a command takes effect before the first step at or after its `at_s`. These mirror
# `STEP_S` / `STEP_SLACK` and `due_step` / `steps_until` in
# `examples/bevy-sitl-poc/src/fleet/autopilot.rs`; change them together.
STEP_S = 0.05
STEP_SLACK = 1e-3

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


def due_step(at_s: float) -> int:
    """The step a command stamped `at_s` takes effect before (`autopilot.rs` `due_step`)."""
    return max(0, math.ceil(at_s / STEP_S - STEP_SLACK))


def steps_until(t_s: float) -> int:
    """How many whole steps lie in `0..=t_s` (`autopilot.rs` `steps_until`)."""
    return max(0, math.floor(t_s / STEP_S + STEP_SLACK))


_NOT_FLYING: frozenset[Phase] = frozenset({"docked", "landing"})
# What a drone is known to be doing once the page has applied a command, until the page's
# telemetry catches up (it is up to half a second behind).
_AFTER_APPLIED: dict[type[FleetCommand], Phase] = {Launch: "climbing", Recall: "returning"}


def _check_waypoints(drone: str, waypoints: Sequence[Waypoint]) -> None:
    if not waypoints:
        raise FleetInvalid(
            InvalidRule.NO_WAYPOINTS, f"{drone}: a route needs at least one waypoint"
        )
    for east, north, up in waypoints:
        if not MIN_UP_M <= up <= MAX_UP_M:
            raise FleetInvalid(
                InvalidRule.HEIGHT_OUT_OF_RANGE,
                f"{drone}: waypoint height {up} m is outside {MIN_UP_M}-{MAX_UP_M} m",
            )
        if abs(east) > BOUND_M or abs(north) > BOUND_M:
            raise FleetInvalid(
                InvalidRule.OUT_OF_BOUNDS,
                f"{drone}: waypoint ({east}, {north}) is outside the +-{BOUND_M} m scene",
            )


def _check_speed(drone: str, route: Route) -> None:
    speed = route.speed_m_s
    if speed is not None and not MIN_SPEED_M_S <= speed <= MAX_SPEED_M_S:
        raise FleetInvalid(
            InvalidRule.SPEED_OUT_OF_RANGE,
            f"{drone}: speed {speed} m/s is outside {MIN_SPEED_M_S}-{MAX_SPEED_M_S} m/s",
        )


@dataclass
class _Pending:
    """The command in flight: its request id and the future its answer settles."""

    request: int
    answer: asyncio.Future[Applied]


class FleetController:
    """One scenario's fleet, as the station commands it."""

    def __init__(
        self,
        scenario_id: str,
        nests: Sequence[Nest],
        log_store: FleetLogStore,
        *,
        timing: FleetTiming | None = None,
        latest_nests: Callable[[], Sequence[Nest]] | None = None,
    ) -> None:
        self._scenario_id = scenario_id
        self._nests = tuple(nests)
        self._latest_nests = latest_nests
        self._log_store = log_store
        self._timing = timing if timing is not None else FleetTiming()
        self._link: SimLink | None = None
        self._hello: SimHello | None = None
        self._session_id: int | None = None
        self._telemetry: Telemetry | None = None
        # Set when the page that sent `_telemetry` has gone: it is kept (the log, `drones()`),
        # but it no longer says what phase a drone is in.
        self._page_gone = False
        self._applied: list[Stamped] = []
        # Every command sent and not yet answered, by request: a late answer to a command the
        # station gave up on still belongs in the log, as the page applied it.
        self._sent: dict[int, FleetCommand] = {}
        # Phases the page's applied commands imply, with the step the page applies them at
        # (`due_step`): telemetry from before that step may still show the old phase.
        self._expected: dict[str, tuple[Phase, int]] = {}
        self._pending: _Pending | None = None
        self._next_request = 1
        self._one_at_a_time = asyncio.Lock()

    @property
    def scenario_id(self) -> str:
        return self._scenario_id

    @property
    def linked(self) -> bool:
        """Whether a page is attached."""
        return self._link is not None

    @property
    def session_id(self) -> int | None:
        """The current (or last) linked session, `None` before any."""
        return self._session_id

    async def send(self, command: FleetCommand) -> Applied:
        """Validates, sends and waits for `command` (see the module docstring)."""
        async with self._one_at_a_time:
            self._validate(command)
            link = self._link
            if link is None:
                raise self._unavailable()
            request = self._next_request
            self._next_request += 1
            pending = _Pending(request, asyncio.get_running_loop().create_future())
            self._pending = pending
            self._sent[request] = command
            try:
                await link.send_text(encode_command(request, command))
                return await self._wait_for(pending)
            finally:
                self._pending = None

    async def _wait_for(self, pending: _Pending) -> Applied:
        """The page's answer to `pending`, or `FleetTimeout` once the ack timer runs out."""
        timeout = FleetTimeout(
            f"the simulation of scenario {self._scenario_id} did not answer request "
            f"{pending.request} in {self._timing.ack_timeout_s} s"
        )
        timer = asyncio.ensure_future(self._timing.sleep(self._timing.ack_timeout_s))
        timer.add_done_callback(
            lambda finished: None if finished.cancelled() else self._settle(pending, timeout)
        )
        try:
            return await pending.answer
        finally:
            timer.cancel()

    def _unavailable(self) -> FleetUnavailable:
        return FleetUnavailable(f"no simulation connected for scenario {self._scenario_id}")

    def _known_drones(self) -> frozenset[str]:
        if self._hello is not None and self._link is not None:
            return frozenset(self._hello.drones)
        return frozenset(drone for nest in self._unlinked_nests() for drone in nest.drone_ids)

    def _unlinked_nests(self) -> tuple[Nest, ...]:
        """The scenario's nests while no page is linked: the latest saved ones (the last known
        when the scenario cannot be read now), since the scene may have changed since the first
        use."""
        if self._latest_nests is not None:
            try:
                self._nests = tuple(self._latest_nests())
            except UnknownRecord:
                pass
        return self._nests

    def _phase_of(self, drone: str) -> Phase:
        if drone in self._expected:
            return self._expected[drone][0]
        if self._telemetry is not None and not self._page_gone:
            for reported in self._telemetry.drones:
                if reported.id == drone:
                    return reported.phase
        return "docked"

    def _validate(self, command: FleetCommand) -> None:
        drone = command.drone
        if drone not in self._known_drones():
            raise FleetInvalid(
                InvalidRule.UNKNOWN_DRONE, f"{drone} is not a drone of scenario {self._scenario_id}"
            )
        phase = self._phase_of(drone)
        match command:
            case Launch(_, route):
                _check_waypoints(drone, route.waypoints)
                _check_speed(drone, route)
                if phase != "docked":
                    raise FleetInvalid(
                        InvalidRule.NOT_DOCKED, f"{drone} is {phase}: launch needs a docked drone"
                    )
            case SetRoute(_, route):
                _check_waypoints(drone, route.waypoints)
                _check_speed(drone, route)
                self._check_flying(drone, phase, "set_route")
            case Detour(_, waypoints):
                _check_waypoints(drone, waypoints)
                self._check_flying(drone, phase, "detour")
            case Recall():
                if phase == "docked":
                    raise FleetInvalid(
                        InvalidRule.ALREADY_DOCKED,
                        f"{drone} is docked: recall needs a drone that has left its pad",
                    )
            case SetActive():
                pass

    @staticmethod
    def _check_flying(drone: str, phase: Phase, what: str) -> None:
        if phase in _NOT_FLYING:
            raise FleetInvalid(
                InvalidRule.NOT_FLYING, f"{drone} is {phase}: {what} needs a drone in flight"
            )

    def drones(self) -> tuple[DroneTelemetry, ...]:
        """Every drone as the last telemetry reported it; empty before any."""
        return self._telemetry.drones if self._telemetry is not None else ()

    def active(self) -> str | None:
        """The drone whose eyes the page shows, per the last telemetry."""
        return self._telemetry.active if self._telemetry is not None else None

    def telemetry_time(self) -> float | None:
        """The simulation time, s, of the linked page's last telemetry; `None` before its first
        and once that page has gone."""
        if self._telemetry is None or self._page_gone:
            return None
        return self._telemetry.sim_t_s

    def session_log(self) -> tuple[Stamped, ...]:
        """The commands applied in the current (or last) session, in order."""
        return tuple(self._applied)

    def attach(self, link: SimLink, hello: SimHello) -> None:
        """Links the page that said `hello`, starting a new logged session."""
        self._link = link
        self._hello = hello
        self._session_id = self._log_store.start_session(self._scenario_id, hello)
        self._telemetry = None
        self._page_gone = False
        self._applied = []
        self._sent = {}
        self._expected = {}

    def receive(self, message: SimMessage) -> None:
        """A frame from the linked page: an answer settles its request, telemetry replaces the
        last."""
        match message:
            case Applied(request, seq, at_s):
                self._on_applied(message, request, seq, at_s)
            case Refused(request):
                self._sent.pop(request, None)
                if self._pending is not None and self._pending.request == request:
                    self._settle(self._pending, FleetRefused(message.reason))
            case Telemetry(sim_t_s):
                self._telemetry = message
                reached = steps_until(sim_t_s)
                self._expected = {
                    drone: (phase, due)
                    for drone, (phase, due) in self._expected.items()
                    if due > reached
                }
            case SimHello():
                pass

    def _on_applied(self, message: Applied, request: int, seq: int, at_s: float) -> None:
        command = self._sent.pop(request, None)
        if command is None or self._session_id is None:
            return
        self._log_store.record(self._session_id, Stamped(seq, at_s, command))
        self._applied.append(Stamped(seq, at_s, command))
        expected = _AFTER_APPLIED.get(type(command))
        if expected is not None:
            self._expected[command.drone] = (expected, due_step(at_s))
        if self._pending is not None and self._pending.request == request:
            self._settle(self._pending, message)

    @staticmethod
    def _settle(pending: _Pending, outcome: Applied | FleetError) -> None:
        if pending.answer.done():
            return
        if isinstance(outcome, Applied):
            pending.answer.set_result(outcome)
        else:
            pending.answer.set_exception(outcome)

    def detach(self) -> None:
        """Unlinks the page; a waiting request fails with `FleetUnavailable`. What the page last
        reported is kept, but its drones' phases no longer decide which commands pass."""
        self._link = None
        self._hello = None
        self._sent = {}
        self._expected = {}
        self._page_gone = True
        if self._pending is not None:
            self._settle(self._pending, self._unavailable())


class FleetRegistry:
    """The server's controllers, one per scenario, built from the scenario's latest manifest on
    first use, and their sessions' log store in the scenario store's file."""

    def __init__(self, store: ScenarioStore, *, timing: FleetTiming | None = None) -> None:
        self._store = store
        self._timing = timing if timing is not None else FleetTiming()
        self._controllers: dict[str, FleetController] = {}
        self.log_store = FleetLogStore(store.db_path)

    def controller(self, scenario_id: str) -> FleetController:
        """The scenario's controller (the same one on every call)."""
        found = self._controllers.get(scenario_id)
        if found is None:
            manifest = self._store.scenario(scenario_id).manifest
            found = FleetController(
                scenario_id,
                nests_of(manifest),
                self.log_store,
                timing=self._timing,
                latest_nests=lambda: nests_of(self._store.scenario(scenario_id).manifest),
            )
            self._controllers[scenario_id] = found
        return found

    async def link(self, scenario_id: str, socket: SimSocket) -> None:
        """Runs one page's link until it closes: the first frame must be a `fleet/v1` `hello`
        (else close `CLOSE_PROTOCOL_ERROR`) naming this scenario (another is a protocol error
        too, and nothing is attached); a scenario already linked closes the newcomer with
        `CLOSE_ALREADY_LINKED`; every later frame goes to the controller (an undecodable one
        closes `CLOSE_PROTOCOL_ERROR`); the close detaches it."""
        try:
            controller = self.controller(scenario_id)
        except UnknownRecord:
            await socket.close(CLOSE_PROTOCOL_ERROR)
            return
        hello = await self._hello_of(socket)
        if hello is None:
            return
        if hello.scenario != scenario_id:
            await socket.close(CLOSE_PROTOCOL_ERROR)
            return
        if controller.linked:
            await socket.close(CLOSE_ALREADY_LINKED)
            return
        controller.attach(socket, hello)
        try:
            await self._pump(controller, socket)
        finally:
            controller.detach()

    @staticmethod
    async def _hello_of(socket: SimSocket) -> SimHello | None:
        first = await socket.receive_text()
        if first is None:
            return None
        try:
            opening = decode_sim_message(first)
        except FleetLinkError:
            opening = None
        if not isinstance(opening, SimHello):
            await socket.close(CLOSE_PROTOCOL_ERROR)
            return None
        return opening

    @staticmethod
    async def _pump(controller: FleetController, socket: SimSocket) -> None:
        while (text := await socket.receive_text()) is not None:
            try:
                message = decode_sim_message(text)
            except FleetLinkError:
                await socket.close(CLOSE_PROTOCOL_ERROR)
                return
            controller.receive(message)
