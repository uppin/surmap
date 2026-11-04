"""The station tools: `StationTools` rpcs the model calls and the chat page polls.

Contracts come from the proto (names, policies, descriptions); handlers answer over a
`StationControl`, here the stub; the agent server mounts them only when it has a station.
"""

from __future__ import annotations

from surmap.agent.contracts import ExecutionMode, OnTimeout, tool_contracts
from surmap.agent.proto import station_tools_pb2 as pb
from surmap.agent.server.app import AgentServerConfig, build_agent_description
from surmap.agent.tools.station import StubStationControl
from surmap.agent.tools.station_handlers import station_tool_handlers
from tests.agent_server_fakes import EmptyWorkspace, NoGlbs
from tests.agent_station_fakes import FakeClock

STATION_TOOLS = pb.DESCRIPTOR.services_by_name["StationTools"]


def a_stub() -> StubStationControl:
    return StubStationControl(clock=FakeClock(), idle_timeout_s=300)


async def call(
    control: StubStationControl, method: str, request: object
) -> pb.StationStatusResponse:
    response = await station_tool_handlers(control)[method](request, None)
    assert isinstance(response, pb.StationStatusResponse)
    return response


def test_the_station_tools_read_start_and_stop_the_gpu_with_their_policies() -> None:
    # Given the StationTools service
    # When its tool contracts are read
    contracts = tool_contracts(STATION_TOOLS)

    # Then status fails fast, and start and stop detach to a job when a GPU is slow
    policies = [
        (
            c.name,
            c.default_execution.mode,
            c.default_execution.timeout_s,
            c.default_execution.on_timeout,
        )
        for c in contracts
    ]
    assert policies == [
        ("get_station_status", ExecutionMode.SYNC, 10, OnTimeout.FAIL),
        ("start_station", ExecutionMode.SYNC, 30, OnTimeout.DETACH),
        ("stop_station", ExecutionMode.SYNC, 30, OnTimeout.DETACH),
    ]


def test_each_station_tool_tells_the_model_what_the_gpu_costs() -> None:
    # Given the StationTools contracts
    descriptions = {c.name: c.description for c in tool_contracts(STATION_TOOLS)}

    # Then status says reading is free, start says SAM starts it anyway, stop says when to
    assert "does not start" in descriptions["get_station_status"]
    assert "first SAM" in descriptions["start_station"]
    assert "idle" in descriptions["stop_station"]


async def test_a_fresh_station_reports_off_through_the_status_tool() -> None:
    # Given an unused station
    # When the status tool is called
    response = await call(a_stub(), "GetStationStatus", pb.GetStationStatusRequest())

    # Then it is off, with its idle timeout and which backend it is
    assert response.status.state == pb.STATION_STATE_OFF
    assert (response.status.idle_timeout_s, response.status.backend) == (300, "stub")


async def test_the_start_tool_brings_the_station_up() -> None:
    # Given an unused station
    control = a_stub()

    # When the start tool is called
    response = await call(control, "StartStation", pb.StartStationRequest())

    # Then it answers ready on one container
    assert (response.status.state, response.status.containers) == (pb.STATION_STATE_READY, 1)


async def test_the_stop_tool_takes_the_station_down() -> None:
    # Given a started station
    control = a_stub()
    control.start()

    # When the stop tool is called
    response = await call(control, "StopStation", pb.StopStationRequest())

    # Then it answers off with no container
    assert (response.status.state, response.status.containers) == (pb.STATION_STATE_OFF, 0)


def mounted_services(station: StubStationControl | None) -> set[str]:
    description = build_agent_description(
        AgentServerConfig(), workspace=EmptyWorkspace(), geometry=NoGlbs(), station=station
    )
    return {module.descriptor.full_name for module in description.services}


def test_an_agent_with_a_station_serves_the_station_tools() -> None:
    # Given an agent server built with a station
    # Then the chat page and the model can reach the station tools
    assert "surmap.agent.v1.StationTools" in mounted_services(a_stub())


def test_an_agent_without_a_station_has_no_station_tools() -> None:
    # Given an agent server built without a station
    # Then it serves no station tools, so the page hides its station indicator
    assert "surmap.agent.v1.StationTools" not in mounted_services(None)
