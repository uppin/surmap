"""The `surmap.agent.v1.FleetTools` handlers over the scenario store and the fleet registry.

These tools task the simulation's drones only (`docs/architecture.md` §1): every command goes
through the scenario's `FleetController` (`surmap.simulation.fleet`) to the linked simulation
page, never to PX4 or a real flight controller.

`fleet_tool_handlers(store, registry)` binds one handler per rpc, by rpc name, in
connect-python's `(request, ctx)` shape, ready for `surmap.agent.services.fleet_module`. Nests
and pads come from the scenario's latest manifest (`fleet_nests.nests_of`); drones from the
controller's last telemetry, every drone docked at its pad before any (and without a link).

Failures are `ConnectError`s (`fleet_error`): `NOT_FOUND` for a scenario the store does not
have or a drone the scene does not have; `INVALID_ARGUMENT` for a command the station refuses
before sending it, its message led by the rule (`no_waypoints: …`); `FAILED_PRECONDITION` with
the page's own reason when the simulation refuses it; `UNAVAILABLE` when no page is linked;
`DEADLINE_EXCEEDED` when the page does not answer in time.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import fleet_tools_pb2 as pb
from surmap.agent.services import Handler
from surmap.simulation.fleet.commands import FleetCommand, Route
from surmap.simulation.fleet.controller import FleetError, FleetRegistry
from surmap.simulation.fleet.link import DroneTelemetry, Phase
from surmap.simulation.fleet_nests import Nest
from surmap.simulation.scenario_store import ScenarioStore

__all__ = [
    "CommandRequest",
    "drone_phase",
    "drone_statuses",
    "fleet_command",
    "fleet_error",
    "fleet_nest",
    "fleet_tool_handlers",
    "flight_route",
]

CommandRequest = (
    pb.LaunchDroneRequest
    | pb.SetRouteRequest
    | pb.AddDetourRequest
    | pb.RecallDroneRequest
    | pb.SetActiveDroneRequest
)
"""A request that becomes one fleet command."""

_RPCS = (
    "ListNests",
    "ListDrones",
    "LaunchDrone",
    "SetRoute",
    "AddDetour",
    "RecallDrone",
    "SetActiveDrone",
    "GetFleetLog",
)


def fleet_tool_handlers(store: ScenarioStore, registry: FleetRegistry) -> Mapping[str, Handler]:
    """Every `FleetTools` rpc, by rpc name, as a `(request, ctx)` handler."""

    async def unimplemented(_request: object, _ctx: object) -> Any:
        # TODO(pr-4): implement
        raise ConnectError(Code.UNIMPLEMENTED, "pr-4: implement")

    return {name: unimplemented for name in _RPCS}


def fleet_error(error: FleetError) -> ConnectError:
    """The Connect error a failed fleet command answers with: `NOT_FOUND` for an unknown drone,
    `INVALID_ARGUMENT` (`"<rule>: <message>"`) for any other `FleetInvalid`,
    `FAILED_PRECONDITION` with a `FleetRefused`'s reason, `UNAVAILABLE` for `FleetUnavailable`,
    `DEADLINE_EXCEEDED` for `FleetTimeout`."""
    # TODO(pr-4): implement
    raise NotImplementedError("pr-4: implement")


def flight_route(route: pb.FlightRoute) -> Route:
    """`route` as the fleet's `Route`: an absent speed and an unspecified end stay `None` (the
    simulation's defaults)."""
    # TODO(pr-4): implement
    raise NotImplementedError("pr-4: implement")


def fleet_command(request: CommandRequest) -> FleetCommand:
    """The fleet command a command request asks for."""
    # TODO(pr-4): implement
    raise NotImplementedError("pr-4: implement")


def drone_phase(phase: Phase) -> pb.DronePhase:
    """A telemetry phase word as the proto's `DronePhase`."""
    # TODO(pr-4): implement
    raise NotImplementedError("pr-4: implement")


def fleet_nest(nest: Nest) -> pb.FleetNest:
    """A scenario's nest as `list_nests` reports it."""
    # TODO(pr-4): implement
    raise NotImplementedError("pr-4: implement")


def drone_statuses(
    nests: Sequence[Nest], telemetry: Sequence[DroneTelemetry]
) -> tuple[pb.DroneStatus, ...]:
    """Every drone of `nests`, nest by nest in drone order: as `telemetry` reports it, or docked
    at its nest's pad, with the pad's heading, when it reports nothing of that drone."""
    # TODO(pr-4): implement
    raise NotImplementedError("pr-4: implement")
