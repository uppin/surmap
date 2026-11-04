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

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from surmap.simulation.fleet.commands import FleetCommand, command_json

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

_PHASES: dict[str, Phase] = {
    "docked": "docked",
    "climbing": "climbing",
    "cruising": "cruising",
    "detouring": "detouring",
    "hovering": "hovering",
    "returning": "returning",
    "landing": "landing",
}


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


def _compact(frame: Mapping[str, object]) -> str:
    return json.dumps(frame, separators=(",", ":"))


def encode_command(request: int, command: FleetCommand) -> str:
    """The `command` frame for `command`, numbered `request`."""
    return _compact({"type": "command", "request": request, "command": command_json(command)})


def _field(frame: Mapping[str, object], key: str, what: str) -> object:
    if key not in frame:
        raise FleetLinkError(f"{what}: missing {key!r}")
    return frame[key]


def _text(frame: Mapping[str, object], key: str, what: str) -> str:
    value = _field(frame, key, what)
    if not isinstance(value, str):
        raise FleetLinkError(f"{what}: {key!r} must be a string")
    return value


def _count(frame: Mapping[str, object], key: str, what: str) -> int:
    value = _field(frame, key, what)
    if isinstance(value, bool) or not isinstance(value, int):
        raise FleetLinkError(f"{what}: {key!r} must be an integer")
    return value


def _seconds(frame: Mapping[str, object], key: str, what: str) -> float:
    value = _field(frame, key, what)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise FleetLinkError(f"{what}: {key!r} must be a number")
    return float(value)


def _phase(frame: Mapping[str, object], what: str) -> Phase:
    value = _text(frame, "phase", what)
    phase = _PHASES.get(value)
    if phase is None:
        raise FleetLinkError(f"{what}: unknown phase {value!r}")
    return phase


def _enu(frame: Mapping[str, object], what: str) -> tuple[float, float, float]:
    value = _field(frame, "enu", what)
    if not isinstance(value, list) or len(value) != 3:
        raise FleetLinkError(f"{what}: 'enu' must be [east, north, up]")
    east, north, up = (_seconds({"axis": axis}, "axis", what) for axis in value)
    return (east, north, up)


def _drone(frame: object) -> DroneTelemetry:
    what = "telemetry drone"
    if not isinstance(frame, dict):
        raise FleetLinkError(f"{what}: must be an object")
    return DroneTelemetry(
        id=_text(frame, "id", what),
        phase=_phase(frame, what),
        enu=_enu(frame, what),
        yaw_deg=_seconds(frame, "yaw_deg", what),
        speed_m_s=_seconds(frame, "speed_m_s", what),
        targets_left=_count(frame, "targets_left", what),
    )


def _list(frame: Mapping[str, object], key: str, what: str) -> list[object]:
    value = _field(frame, key, what)
    if not isinstance(value, list):
        raise FleetLinkError(f"{what}: {key!r} must be a list")
    return value


def decode_sim_message(text: str) -> SimMessage:
    """The message a simulation frame carries; `FleetLinkError` for anything else (not JSON, an
    unknown `type`, a protocol other than `fleet/v1`, a missing field, an unknown phase)."""
    try:
        frame = json.loads(text)
    except ValueError as error:
        raise FleetLinkError(f"not a JSON frame: {error}") from error
    if not isinstance(frame, dict):
        raise FleetLinkError("a frame is a JSON object")
    kind = frame.get("type")
    match kind:
        case "hello":
            protocol = _text(frame, "protocol", "hello")
            if protocol != PROTOCOL:
                raise FleetLinkError(f"protocol {protocol!r} is not {PROTOCOL!r}")
            drones = _list(frame, "drones", "hello")
            if not all(isinstance(drone, str) for drone in drones):
                raise FleetLinkError("hello: 'drones' are drone ids")
            return SimHello(
                scenario=_text(frame, "scenario", "hello"),
                sim_t_s=_seconds(frame, "sim_t_s", "hello"),
                drones=tuple(str(drone) for drone in drones),
            )
        case "applied":
            return Applied(
                request=_count(frame, "request", "applied"),
                seq=_count(frame, "seq", "applied"),
                at_s=_seconds(frame, "at_s", "applied"),
            )
        case "refused":
            return Refused(
                request=_count(frame, "request", "refused"),
                at_s=_seconds(frame, "at_s", "refused"),
                reason=_text(frame, "reason", "refused"),
            )
        case "telemetry":
            active = _field(frame, "active", "telemetry")
            if active is not None and not isinstance(active, str):
                raise FleetLinkError("telemetry: 'active' must be a drone id or null")
            return Telemetry(
                sim_t_s=_seconds(frame, "sim_t_s", "telemetry"),
                active=active,
                drones=tuple(_drone(drone) for drone in _list(frame, "drones", "telemetry")),
            )
        case _:
            raise FleetLinkError(f"unknown message type {kind!r}")


def _drone_json(drone: DroneTelemetry) -> dict[str, object]:
    return {
        "id": drone.id,
        "phase": drone.phase,
        "enu": list(drone.enu),
        "yaw_deg": drone.yaw_deg,
        "speed_m_s": drone.speed_m_s,
        "targets_left": drone.targets_left,
    }


def encode_sim_message(message: SimMessage) -> str:
    """The frame the simulation sends for `message` (the inverse of `decode_sim_message`)."""
    match message:
        case SimHello(scenario, sim_t_s, drones):
            return _compact(
                {
                    "type": "hello",
                    "protocol": PROTOCOL,
                    "scenario": scenario,
                    "sim_t_s": sim_t_s,
                    "drones": list(drones),
                }
            )
        case Applied(request, seq, at_s):
            return _compact({"type": "applied", "request": request, "seq": seq, "at_s": at_s})
        case Refused(request, at_s, reason):
            return _compact({"type": "refused", "request": request, "at_s": at_s, "reason": reason})
        case Telemetry(sim_t_s, active, drones):
            return _compact(
                {
                    "type": "telemetry",
                    "sim_t_s": sim_t_s,
                    "active": active,
                    "drones": [_drone_json(drone) for drone in drones],
                }
            )
