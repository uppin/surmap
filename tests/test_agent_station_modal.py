"""`ModalStationControl`: the station as a deployed Modal app, read and driven by the SDK.

What only the Modal implementation does, over `FakeModalFunction`: the state comes from the
function's live stats and never from an HTTP call to the station, a start is a health GET
(which is what boots a container), and a stop closes the agent's own link and scales down.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from surmap.agent.tools.station import StationState, StationUnavailable
from surmap.agent.tools.station_modal import ModalStationControl
from tests.agent_station_fakes import (
    STATION_URL,
    FakeClock,
    FakeModalFunction,
    FakeProbe,
    RecordingLinks,
    a_frame,
)


@dataclass
class Rig:
    control: ModalStationControl
    function: FakeModalFunction
    probe: FakeProbe
    links: RecordingLinks
    clock: FakeClock


def a_rig(*, answers: list[int] | None = None, idle_s: int = 300) -> Rig:
    clock = FakeClock()
    function = FakeModalFunction()
    probe = FakeProbe(function, answers if answers is not None else [200])
    links = RecordingLinks()
    control = ModalStationControl(
        function,
        probe=probe,
        connect=links,
        token="survey-token",
        prompt="object",
        clock=clock,
        sleep=clock.sleep,
        idle_timeout_s=idle_s,
        start_timeout_s=600,
    )
    return Rig(control, function, probe, links, clock)


def test_reading_the_status_never_calls_the_station() -> None:
    # Given an off station
    rig = a_rig()

    # When its status is read several times
    for _ in range(3):
        rig.control.status()

    # Then no health check went out, so no GPU was started by looking
    assert rig.probe.calls == []


def test_a_request_waiting_for_a_gpu_reads_as_queued() -> None:
    # Given a request queued on the function with no container yet
    rig = a_rig()
    rig.function.queued = 1

    # When the status is read
    status = rig.control.status()

    # Then the station is queued, waiting for a GPU
    assert (status.state, status.containers) == (StationState.QUEUED, 0)
    assert "GPU" in status.detail


def test_a_container_nobody_has_health_checked_reads_as_starting() -> None:
    # Given a container on the function this agent has not seen answer
    rig = a_rig()
    rig.function.containers = 1

    # When the status is read
    status = rig.control.status()

    # Then it is starting, not ready
    assert status.state == StationState.STARTING


def test_starting_health_checks_the_station_until_it_answers() -> None:
    # Given a station that answers its health check only on the third try
    rig = a_rig(answers=[503, 503, 200])

    # When it is started
    status = rig.control.start()

    # Then it polled the station's health URL until it answered, and is ready
    assert rig.probe.calls == [f"{STATION_URL}/health/is_alive"] * 3
    assert status.state == StationState.READY


def test_starting_lets_the_station_scale_down_only_after_the_idle_timeout() -> None:
    # Given an agent with a 120 s idle timeout
    rig = a_rig(idle_s=120)

    # When it starts the station
    rig.control.start()

    # Then Modal keeps an idle container that long, and no longer
    assert rig.function.autoscaler_updates[-1] == {"scaledown_window": 120}


def test_a_station_that_never_answers_fails_to_start_and_reads_as_an_error() -> None:
    # Given a station whose health check never succeeds
    rig = a_rig(answers=[503])

    # When it is started
    with pytest.raises(StationUnavailable, match="health"):
        rig.control.start()

    # Then the status says why, until the next start
    status = rig.control.status()
    assert status.state == StationState.ERROR
    assert "health" in status.detail


def test_stopping_closes_the_agents_link_and_scales_the_station_down() -> None:
    # Given a station the agent has segmented a frame on
    rig = a_rig()
    rig.control.detector().track(a_frame())

    # When it is stopped
    rig.control.stop()

    # Then the agent's link is closed and Modal lets idle containers go within 2 s
    assert [detector.closed for detector in rig.links.detectors] == [True]
    assert rig.function.autoscaler_updates[-1] == {"min_containers": 0, "scaledown_window": 2}


def test_a_container_still_serving_another_client_reads_as_stopping() -> None:
    # Given a ready station whose container also serves another client's stream
    rig = a_rig()
    rig.control.start()
    rig.function.running_inputs = 1

    # When it is stopped
    status = rig.control.stop()

    # Then it is stopping until that stream ends, and says so
    assert (status.state, status.containers) == (StationState.STOPPING, 1)
    assert "another client" in status.detail


def test_a_stopped_container_that_has_not_left_yet_reads_as_leaving() -> None:
    # Given a ready station whose idle container takes a moment to leave once stopped
    rig = a_rig()
    rig.control.start()
    rig.function.leaves_at_once = False

    # When it is stopped
    status = rig.control.stop()

    # Then it is stopping, and says it waits for the container to leave, not for a client
    assert status.state == StationState.STOPPING
    assert "leave" in status.detail and "client" not in status.detail


def test_the_link_reaches_the_station_url_with_the_survey_token_and_the_prompt() -> None:
    # Given an off station
    rig = a_rig()

    # When the first frame is tracked
    rig.control.detector().track(a_frame())

    # Then one link was opened to the deployed URL, with the token and the prompt
    assert rig.links.opened == [(STATION_URL, "survey-token", "object")]


def test_an_unreachable_modal_reads_as_an_error_instead_of_raising() -> None:
    # Given a Modal API the agent cannot reach
    rig = a_rig()
    rig.function.unreachable = "token rejected"

    # When the status is read
    status = rig.control.status()

    # Then it is an error naming the cause
    assert status.state == StationState.ERROR
    assert "token rejected" in status.detail
