"""Test doubles for the fleet link: a simulation page speaking `fleet/v1` over a real WebSocket,
in-memory links and sockets for the controller and registry, and an instant, recording clock.

The fake page builds and reads its frames as plain JSON, so it pins the wire shapes rather than
echoing the station's own codec.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

from surmap.simulation.fleet.commands import Launch, Route
from surmap.simulation.fleet.link import SimHello
from surmap.simulation.scenario_manifest import load_presets
from surmap.simulation.scenario_store import ScenarioStore
from tests.agent_server_fakes import STEP_TIMEOUT_S
from tests.sim_fakes import POC_ASSETS

PROTOCOL = "fleet/v1"
EARTHQUAKE_FLEET_DRONES = ("nest-sw-d1", "nest-sw-d2", "nest-ne-d1", "nest-ne-d2", "nest-roof-d1")
QUAKE_FLEET = "quake-fleet"
"""The id `a_fleet_store` gives its earthquake-fleet scenario."""

# The first command of `tests/fixtures/fleet/commands.json`.
THE_SHARED_LAUNCH = Launch(
    "nest-sw-d1",
    Route(((-20.0, 0.0, 15.0), (-20.0, 60.0, 18.0)), speed_m_s=6.0, on_complete="hover"),
)


def a_fleet_store(tmp_path: Path) -> ScenarioStore:
    """A scenario store holding the earthquake-fleet scenario `QUAKE_FLEET`."""
    store = ScenarioStore(
        db_path=tmp_path / "simulation.sqlite",
        library_dir=tmp_path / "library",
        presets=load_presets(POC_ASSETS),
    )
    store.create_scenario("Quake fleet", "earthquake-fleet")
    return store


def a_hello() -> SimHello:
    """The page's hello for `QUAKE_FLEET` at 0 s, naming its five drones."""
    return SimHello(QUAKE_FLEET, 0.0, EARTHQUAKE_FLEET_DRONES)


Frame = dict[str, Any]


def frame_text(frame: Frame) -> str:
    """A frame as the page sends it: compact JSON."""
    return json.dumps(frame, separators=(",", ":"))


def hello_frame(
    scenario: str,
    drones: Sequence[str] = EARTHQUAKE_FLEET_DRONES,
    *,
    protocol: str = PROTOCOL,
    sim_t_s: float = 0.0,
) -> Frame:
    return {
        "type": "hello",
        "protocol": protocol,
        "scenario": scenario,
        "sim_t_s": sim_t_s,
        "drones": list(drones),
    }


def telemetry_frame(sim_t_s: float, active: str | None, drones: Sequence[Frame] = ()) -> Frame:
    return {"type": "telemetry", "sim_t_s": sim_t_s, "active": active, "drones": list(drones)}


def drone_frame(
    drone: str,
    phase: str,
    enu: tuple[float, float, float],
    *,
    yaw_deg: float = 0.0,
    speed_m_s: float = 0.0,
    targets_left: int = 0,
) -> Frame:
    return {
        "id": drone,
        "phase": phase,
        "enu": list(enu),
        "yaw_deg": yaw_deg,
        "speed_m_s": speed_m_s,
        "targets_left": targets_left,
    }


# ---- the clock --------------------------------------------------------------------------------


@dataclass
class RecordingSleep:
    """An `asyncio.sleep` that returns at once and remembers how long it was asked to wait."""

    waits: list[float] = field(default_factory=list)

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)
        await asyncio.sleep(0)


async def eventually(condition: Callable[[], bool], within_s: float = STEP_TIMEOUT_S) -> None:
    """Waits until `condition()` holds; fails the test after `within_s`."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + within_s
    while not condition():
        if loop.time() > deadline:
            raise AssertionError(f"not true within {within_s} s")
        await asyncio.sleep(0.01)


async def settle(turns: int = 20) -> None:
    """Lets every ready task run a few steps."""
    for _ in range(turns):
        await asyncio.sleep(0)


# ---- in-memory ends ---------------------------------------------------------------------------


@dataclass
class RecordingLink:
    """A linked page that never answers by itself: it keeps every frame the controller sends."""

    sent: list[Frame] = field(default_factory=list)
    _arrived: asyncio.Queue[Frame] = field(default_factory=asyncio.Queue)

    async def send_text(self, text: str) -> None:
        frame: Frame = json.loads(text)
        self.sent.append(frame)
        await self._arrived.put(frame)

    async def next_frame(self) -> Frame:
        """The next frame the controller sends."""
        return await asyncio.wait_for(self._arrived.get(), STEP_TIMEOUT_S)


@dataclass
class ScriptedSocket:
    """A page's socket as the registry sees it: frames the test says, frames the station sends,
    and the code it was closed with."""

    sent: list[Frame] = field(default_factory=list)
    closed_with: int | None = None
    _inbound: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue)
    _closed: asyncio.Event = field(default_factory=asyncio.Event)

    def say(self, *frames: Frame) -> None:
        for frame in frames:
            self._inbound.put_nowait(frame_text(frame))

    def say_text(self, text: str) -> None:
        self._inbound.put_nowait(text)

    def hang_up(self) -> None:
        self._inbound.put_nowait(None)

    async def receive_text(self) -> str | None:
        return await self._inbound.get()

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def close(self, code: int) -> None:
        self.closed_with = code
        self._closed.set()
        self._inbound.put_nowait(None)

    async def close_code(self) -> int | None:
        """The code the station closed this socket with, once it has."""
        await asyncio.wait_for(self._closed.wait(), STEP_TIMEOUT_S)
        return self.closed_with


# ---- the page over a real socket --------------------------------------------------------------


@dataclass(frozen=True)
class Applies:
    """Answer the next command `applied`, as log entry `seq` at simulation time `at_s`."""

    seq: int
    at_s: float


@dataclass(frozen=True)
class Refuses:
    """Answer the next command `refused` at `at_s`, for `reason`."""

    at_s: float
    reason: str


@dataclass(frozen=True)
class StaysSilent:
    """Never answer the next command."""


Answer = Applies | Refuses | StaysSilent


class FakeSim:
    """A simulation page linked to the station: it answers each command with the next scripted
    answer (`applied` with the next seq at 1 s steps once the script runs out) and sends
    telemetry when told to."""

    def __init__(self, socket: ClientConnection, answers: Iterable[Answer]) -> None:
        self._socket = socket
        self._answers = list(answers)
        self.commands: list[Frame] = []
        """The fleet commands received, in order (the `command` of each frame)."""
        self.requests: list[int] = []

    async def send_telemetry(self, frame: Frame) -> None:
        await self._socket.send(frame_text(frame))

    async def close_code(self) -> int | None:
        """The code the station closed the link with, once it has."""
        await asyncio.wait_for(self._socket.wait_closed(), STEP_TIMEOUT_S)
        return self._socket.close_code

    async def answer_all(self) -> None:
        with suppress(ConnectionClosed):
            async for text in self._socket:
                frame: Frame = json.loads(text)
                self.commands.append(frame["command"])
                self.requests.append(frame["request"])
                await self._answer(frame["request"], self._next_answer())

    def _next_answer(self) -> Answer:
        if self._answers:
            return self._answers.pop(0)
        return Applies(seq=len(self.commands), at_s=float(len(self.commands)))

    async def _answer(self, request: int, answer: Answer) -> None:
        if isinstance(answer, Applies):
            reply: Frame = {
                "type": "applied",
                "request": request,
                "seq": answer.seq,
                "at_s": answer.at_s,
            }
        elif isinstance(answer, Refuses):
            reply = {
                "type": "refused",
                "request": request,
                "at_s": answer.at_s,
                "reason": answer.reason,
            }
        else:
            return
        await self._socket.send(frame_text(reply))


@asynccontextmanager
async def a_sim_page(
    address: str,
    scenario: str,
    answers: Iterable[Answer] = (),
    drones: Sequence[str] = EARTHQUAKE_FLEET_DRONES,
) -> AsyncIterator[FakeSim]:
    """A page at `ws://<address>/sim/fleet?scenario=<scenario>` that has said hello."""
    url = f"ws://{address}/sim/fleet?scenario={scenario}"
    async with websockets.connect(url, open_timeout=STEP_TIMEOUT_S) as socket:
        with suppress(ConnectionClosed):
            await socket.send(frame_text(hello_frame(scenario, drones)))
        sim = FakeSim(socket, answers)
        answering = asyncio.create_task(sim.answer_all())
        try:
            yield sim
        finally:
            answering.cancel()
            with suppress(asyncio.CancelledError):
                await answering
