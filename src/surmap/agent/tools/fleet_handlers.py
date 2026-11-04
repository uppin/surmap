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

`drone_map_status_handler(store, perception)` is `DroneMapStatus`, registered beside them: each
drone's own map and segmentation on the station's stereo bridge
(`surmap.simulation.fleet.perception`), `UNAVAILABLE` when no page streams the scenario.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import fleet_tools_pb2 as pb
from surmap.agent.proto import simulation_tools_pb2 as sim_pb
from surmap.agent.services import Handler
from surmap.agent.tools.onboard import OnboardModels
from surmap.agent.tools.simulation_core import blocking
from surmap.simulation.fleet.commands import (
    Detour,
    FleetCommand,
    Launch,
    OnComplete,
    Recall,
    Route,
    SetActive,
    SetRoute,
    Waypoint,
)
from surmap.simulation.fleet.controller import (
    FleetController,
    FleetError,
    FleetInvalid,
    FleetRefused,
    FleetTimeout,
    FleetUnavailable,
    InvalidRule,
)
from surmap.simulation.fleet.link import DroneTelemetry, Phase
from surmap.simulation.fleet.log_store import UnknownSession
from surmap.simulation.fleet.perception import DroneCounts, PerceptionRegistry
from surmap.simulation.fleet.registry import FleetRegistry
from surmap.simulation.fleet_nests import Nest, nests_of
from surmap.simulation.scenario_store import ScenarioStore

__all__ = [
    "CommandRequest",
    "drone_map_counts",
    "drone_map_status_handler",
    "drone_phase",
    "drone_statuses",
    "fleet_command",
    "fleet_error",
    "fleet_nest",
    "fleet_tool_handlers",
    "flight_route",
    "set_onboard_model_handler",
]

CommandRequest = (
    pb.LaunchDroneRequest
    | pb.SetRouteRequest
    | pb.AddDetourRequest
    | pb.RecallDroneRequest
    | pb.SetActiveDroneRequest
)
"""A request that becomes one fleet command."""

_PHASES: Mapping[Phase, pb.DronePhase] = {
    "docked": pb.DRONE_PHASE_DOCKED,
    "climbing": pb.DRONE_PHASE_CLIMBING,
    "cruising": pb.DRONE_PHASE_CRUISING,
    "detouring": pb.DRONE_PHASE_DETOURING,
    "hovering": pb.DRONE_PHASE_HOVERING,
    "returning": pb.DRONE_PHASE_RETURNING,
    "landing": pb.DRONE_PHASE_LANDING,
}
_ROUTE_ENDS: Mapping[pb.RouteEnd, OnComplete | None] = {
    pb.ROUTE_END_UNSPECIFIED: None,
    pb.ROUTE_END_RETURN: "return",
    pb.ROUTE_END_HOVER: "hover",
}


def fleet_tool_handlers(store: ScenarioStore, registry: FleetRegistry) -> Mapping[str, Handler]:
    """Every `FleetTools` rpc, by rpc name, as a `(request, ctx)` handler.

    Each resolves the scenario through `store` first, so an unknown one is `NOT_FOUND` before
    the registry is touched.
    """

    async def nests(scenario_id: str) -> tuple[Nest, ...]:
        return await blocking(lambda: nests_of(store.scenario(scenario_id).manifest))

    async def controller(scenario_id: str) -> FleetController:
        await nests(scenario_id)
        return registry.controller(scenario_id)

    async def list_nests(request: pb.ListNestsRequest, _ctx: object) -> pb.ListNestsResponse:
        found = await nests(request.scenario_id)
        return pb.ListNestsResponse(nests=[fleet_nest(nest) for nest in found])

    async def list_drones(request: pb.ListDronesRequest, _ctx: object) -> pb.ListDronesResponse:
        found = await nests(request.scenario_id)
        fleet = await controller(request.scenario_id)
        if not fleet.linked:
            return pb.ListDronesResponse(linked=False, drones=drone_statuses(found, ()))
        return pb.ListDronesResponse(
            linked=True,
            active=fleet.active() or "",
            drones=drone_statuses(found, fleet.drones()),
            sim_t_s=fleet.telemetry_time(),
        )

    async def command(request: CommandRequest, _ctx: object) -> pb.FleetCommandResult:
        fleet = await controller(request.scenario_id)
        try:
            applied = await fleet.send(fleet_command(request))
        except FleetError as error:
            raise fleet_error(error) from error
        return pb.FleetCommandResult(seq=applied.seq, at_s=applied.at_s)

    async def get_fleet_log(request: pb.GetFleetLogRequest, _ctx: object) -> pb.GetFleetLogResponse:
        await nests(request.scenario_id)
        sessions = await asyncio.to_thread(registry.log_store.sessions, request.scenario_id)
        if not sessions:
            raise ConnectError(
                Code.NOT_FOUND, f"no fleet session of scenario {request.scenario_id} yet"
            )
        session_id = (
            request.session_id if request.HasField("session_id") else sessions[-1].session_id
        )
        if session_id not in {session.session_id for session in sessions}:
            raise ConnectError(
                Code.NOT_FOUND,
                f"no fleet session {session_id} of scenario {request.scenario_id}",
            )
        try:
            log = await asyncio.to_thread(registry.log_store.export_jsonl, session_id)
        except UnknownSession as error:
            raise ConnectError(Code.NOT_FOUND, str(error)) from error
        return pb.GetFleetLogResponse(session_id=session_id, fleet_log_jsonl=log)

    handlers: dict[str, Handler] = {
        "ListNests": list_nests,
        "ListDrones": list_drones,
        "LaunchDrone": command,
        "SetRoute": command,
        "AddDetour": command,
        "RecallDrone": command,
        "SetActiveDrone": command,
        "GetFleetLog": get_fleet_log,
    }
    return handlers


def fleet_error(error: FleetError) -> ConnectError:
    """The Connect error a failed fleet command answers with: `NOT_FOUND` for an unknown drone,
    `INVALID_ARGUMENT` (`"<rule>: <message>"`) for any other `FleetInvalid`,
    `FAILED_PRECONDITION` with a `FleetRefused`'s reason, `UNAVAILABLE` for `FleetUnavailable`,
    `DEADLINE_EXCEEDED` for `FleetTimeout`."""
    match error:
        case FleetInvalid(rule=InvalidRule.UNKNOWN_DRONE):
            return ConnectError(Code.NOT_FOUND, str(error))
        case FleetInvalid(rule=rule):
            return ConnectError(Code.INVALID_ARGUMENT, f"{rule.value}: {error}")
        case FleetRefused(reason=reason):
            return ConnectError(Code.FAILED_PRECONDITION, reason)
        case FleetUnavailable():
            return ConnectError(Code.UNAVAILABLE, str(error))
        case FleetTimeout():
            return ConnectError(Code.DEADLINE_EXCEEDED, str(error))
        case _:
            return ConnectError(Code.INTERNAL, str(error))


def _waypoints(points: Sequence[sim_pb.EnuPoint]) -> tuple[Waypoint, ...]:
    return tuple((point.east, point.north, point.up) for point in points)


def flight_route(route: pb.FlightRoute) -> Route:
    """`route` as the fleet's `Route`: an absent speed and an unspecified end stay `None` (the
    simulation's defaults)."""
    return Route(
        _waypoints(route.waypoints),
        speed_m_s=route.speed_m_s if route.HasField("speed_m_s") else None,
        on_complete=_ROUTE_ENDS[route.on_complete],
    )


def fleet_command(request: CommandRequest) -> FleetCommand:
    """The fleet command a command request asks for."""
    match request:
        case pb.LaunchDroneRequest():
            return Launch(request.drone_id, flight_route(request.route))
        case pb.SetRouteRequest():
            return SetRoute(request.drone_id, flight_route(request.route))
        case pb.AddDetourRequest():
            return Detour(request.drone_id, _waypoints(request.waypoints))
        case pb.RecallDroneRequest():
            return Recall(request.drone_id)
        case pb.SetActiveDroneRequest():
            return SetActive(request.drone_id)


def drone_phase(phase: Phase) -> pb.DronePhase:
    """A telemetry phase word as the proto's `DronePhase`."""
    return _PHASES[phase]


def _enu(east: float, north: float, up: float) -> sim_pb.EnuPoint:
    return sim_pb.EnuPoint(east=east, north=north, up=up)


def fleet_nest(nest: Nest) -> pb.FleetNest:
    """A scenario's nest as `list_nests` reports it."""
    return pb.FleetNest(
        id=nest.id,
        position=_enu(*nest.pad_enu),
        yaw_deg=nest.yaw_deg,
        drone_ids=list(nest.drone_ids),
    )


def drone_statuses(
    nests: Sequence[Nest], telemetry: Sequence[DroneTelemetry]
) -> tuple[pb.DroneStatus, ...]:
    """Every drone of `nests`, nest by nest in drone order: as `telemetry` reports it, or docked
    at its nest's pad, with the pad's heading, when it reports nothing of that drone."""
    seen = {drone.id: drone for drone in telemetry}
    statuses: list[pb.DroneStatus] = []
    for nest in nests:
        for drone_id in nest.drone_ids:
            reported = seen.get(drone_id)
            if reported is None:
                statuses.append(
                    pb.DroneStatus(
                        id=drone_id,
                        nest=nest.id,
                        phase=pb.DRONE_PHASE_DOCKED,
                        position=_enu(*nest.pad_enu),
                        yaw_deg=nest.yaw_deg,
                    )
                )
            else:
                statuses.append(
                    pb.DroneStatus(
                        id=drone_id,
                        nest=nest.id,
                        phase=drone_phase(reported.phase),
                        position=_enu(*reported.enu),
                        yaw_deg=reported.yaw_deg,
                        speed_m_s=reported.speed_m_s,
                        targets_left=reported.targets_left,
                    )
                )
    return tuple(statuses)


def drone_map_status_handler(store: ScenarioStore, perception: PerceptionRegistry) -> Handler:
    """`DroneMapStatus` as a `(request, ctx)` handler: every drone of the scenario's nests, nest
    by nest in drone order (or only the drone the request names), with its session's counts from
    the scenario's connected bridge page, zeros for a drone that never streamed. `NOT_FOUND` for
    a scenario the store does not have or a drone the scene does not have, `UNAVAILABLE` when no
    page streams the scenario."""

    async def drone_map_status(
        request: pb.DroneMapStatusRequest, _ctx: object
    ) -> pb.DroneMapStatusResponse:
        nests = await blocking(lambda: nests_of(store.scenario(request.scenario_id).manifest))
        drone_ids = [drone_id for nest in nests for drone_id in nest.drone_ids]
        requested = request.drone_id if request.HasField("drone_id") else None
        if requested is not None and requested not in drone_ids:
            raise ConnectError(Code.NOT_FOUND, f"{requested} is not a drone of this scene")
        page = perception.perception(request.scenario_id)
        if page is None:
            raise ConnectError(Code.UNAVAILABLE, f"no page streams scenario {request.scenario_id}")
        by_id = {counts.drone_id: counts for counts in page.counts()}
        wanted = [requested] if requested is not None else drone_ids
        return pb.DroneMapStatusResponse(
            drones=[
                drone_map_counts(
                    by_id.get(
                        drone_id,
                        DroneCounts(
                            drone_id=drone_id,
                            frames=0,
                            posed=0,
                            lost=0,
                            keyframes=0,
                            dropped=0,
                            segmented_frames=0,
                            detections=0,
                            processing=False,
                            last_t_ns=None,
                        ),
                    )
                )
                for drone_id in wanted
            ]
        )

    return drone_map_status


def set_onboard_model_handler(
    store: ScenarioStore, perception: PerceptionRegistry, onboard: OnboardModels
) -> Handler:
    """`SetOnboardModel` as a `(request, ctx)` handler."""

    async def set_onboard_model(
        request: pb.SetOnboardModelRequest, _ctx: object
    ) -> pb.SetOnboardModelResponse:
        raise NotImplementedError

    return set_onboard_model


def drone_map_counts(counts: DroneCounts) -> pb.DroneMapCounts:
    """A drone session's counts as `drone_map_status` reports them (`last_t_ns` 0 before any
    frame; `error` set only for a session whose map failed)."""
    return pb.DroneMapCounts(
        drone_id=counts.drone_id,
        frames=counts.frames,
        posed=counts.posed,
        lost=counts.lost,
        keyframes=counts.keyframes,
        segmented_frames=counts.segmented_frames,
        detections=counts.detections,
        processing=counts.processing,
        last_t_ns=counts.last_t_ns if counts.last_t_ns is not None else 0,
        error=counts.error,
    )
