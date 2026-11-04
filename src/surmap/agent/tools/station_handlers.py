"""The `StationTools` handlers: status, start and stop over a `StationControl`.

The control's calls block (a start waits for a GPU), so each runs on a worker thread; the
execution policy detaches a slow start to a job.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import station_tools_pb2 as pb
from surmap.agent.services import Handler
from surmap.agent.tools.station import (
    StationControl,
    StationState,
    StationStatus,
    StationUnavailable,
)

_STATES: dict[StationState, pb.StationState] = {
    StationState.OFF: pb.STATION_STATE_OFF,
    StationState.QUEUED: pb.STATION_STATE_QUEUED,
    StationState.STARTING: pb.STATION_STATE_STARTING,
    StationState.READY: pb.STATION_STATE_READY,
    StationState.STOPPING: pb.STATION_STATE_STOPPING,
    StationState.ERROR: pb.STATION_STATE_ERROR,
}


def station_tool_handlers(control: StationControl) -> Mapping[str, Handler]:
    """Every `StationTools` rpc, by rpc name, over `control`."""

    def bind(action: Callable[[], StationStatus]) -> Handler:
        async def serve(_request: object, _ctx: object) -> pb.StationStatusResponse:
            try:
                status = await asyncio.to_thread(action)
            except StationUnavailable as exc:
                raise ConnectError(Code.UNAVAILABLE, str(exc)) from exc
            return pb.StationStatusResponse(status=status_message(status))

        return serve

    return {
        "GetStationStatus": bind(control.status),
        "StartStation": bind(control.start),
        "StopStation": bind(control.stop),
    }


def status_message(status: StationStatus) -> pb.StationStatus:
    return pb.StationStatus(
        state=_STATES[status.state],
        detail=status.detail,
        containers=status.containers,
        idle_timeout_s=status.idle_timeout_s,
        idle_for_s=status.idle_for_s,
        backend=status.backend,
    )
