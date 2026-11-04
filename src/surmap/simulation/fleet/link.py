"""`fleet/v1`: the JSON text frames between the station and a linked simulation page.

| Direction | Message |
|---|---|
| sim → station | `hello` — protocol, scenario, simulation time, the scene's drone ids |
| station → sim | `command` — a request id and one fleet command |
| sim → station | `applied` — the request, the log `seq` it took and the simulation time |
| sim → station | `refused` — the request, the simulation time and the simulation's reason |
| sim → station | `telemetry` — every drone's phase and pose, twice a second |

Frames are compact JSON (`separators=(",", ":")`) with keys in the order above; the goldens in
`tests/fixtures/fleet_link/` are shared with the renderer's `fleet/link.rs`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from surmap.simulation.fleet.commands import FleetCommand

__all__ = [
    "CLOSE_ALREADY_LINKED",
    "CLOSE_PROTOCOL_ERROR",
    "PROTOCOL",
    "Applied",
    "DroneTelemetry",
    "FleetLinkError",
    "Phase",
    "Refused",
    "SimHello",
    "SimMessage",
    "Telemetry",
    "decode_sim_message",
    "encode_command",
    "encode_sim_message",
]

PROTOCOL = "fleet/v1"
# The socket is closed with this code on an unknown message type or another protocol.
CLOSE_PROTOCOL_ERROR = 4400
# A second page linking a scenario that already has one is closed with this code.
CLOSE_ALREADY_LINKED = 4409

Phase = Literal["docked", "climbing", "cruising", "detouring", "hovering", "returning", "landing"]
"""The renderer's `autopilot::Phase`, as telemetry names it."""


class FleetLinkError(ValueError):
    """A frame that is not `fleet/v1`."""


@dataclass(frozen=True)
class SimHello:
    """The page's first frame: which scenario it runs, at what simulation time, with which
    drones."""

    scenario: str
    sim_t_s: float
    drones: tuple[str, ...]


@dataclass(frozen=True)
class Applied:
    """The simulation applied request `request` as log entry `seq`, at simulation time `at_s`."""

    request: int
    seq: int
    at_s: float


@dataclass(frozen=True)
class Refused:
    """The simulation refused request `request` at `at_s`, for `reason`."""

    request: int
    at_s: float
    reason: str


@dataclass(frozen=True)
class DroneTelemetry:
    """One drone as the page last saw it."""

    id: str
    phase: Phase
    enu: tuple[float, float, float]
    yaw_deg: float
    speed_m_s: float
    targets_left: int


@dataclass(frozen=True)
class Telemetry:
    """Every drone of the scene at `sim_t_s`, and the one whose eyes are shown."""

    sim_t_s: float
    active: str | None
    drones: tuple[DroneTelemetry, ...]


SimMessage = SimHello | Applied | Refused | Telemetry


def encode_command(request: int, command: FleetCommand) -> str:
    """The `command` frame for `command`, numbered `request`."""
    # TODO(pr-3): implement
    raise NotImplementedError("pr-3: implement")


def decode_sim_message(text: str) -> SimMessage:
    """The message a simulation frame carries; `FleetLinkError` for anything else (not JSON, an
    unknown `type`, a protocol other than `fleet/v1`, a missing field, an unknown phase)."""
    # TODO(pr-3): implement
    raise NotImplementedError("pr-3: implement")


def encode_sim_message(message: SimMessage) -> str:
    """The frame the simulation sends for `message` (the inverse of `decode_sim_message`)."""
    # TODO(pr-3): implement
    raise NotImplementedError("pr-3: implement")
