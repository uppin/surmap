"""The `StationControl` contract, run against both implementations.

A station is a SAM GPU the agent brings up on first use and takes down when idle. The stub
and the Modal control (over a fake Modal function) must behave the same through the
interface: states, start and stop, the first SAM frame starting it, the idle timeout.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from surmap.agent.tools.station import (
    IdleTicker,
    StationControl,
    StationState,
    StationStatus,
    StubStationControl,
)
from surmap.agent.tools.station_modal import ModalStationControl
from tests.agent_station_fakes import (
    FakeClock,
    FakeModalFunction,
    FakeProbe,
    RecordingLinks,
    a_frame,
    labels,
)

IDLE_S = 300


@dataclass
class Station:
    control: StationControl
    clock: FakeClock


def a_stub_station() -> Station:
    clock = FakeClock()
    return Station(StubStationControl(clock=clock, idle_timeout_s=IDLE_S), clock)


def a_modal_station() -> Station:
    clock = FakeClock()
    function = FakeModalFunction()
    control = ModalStationControl(
        function,
        probe=FakeProbe(function),
        connect=RecordingLinks(),
        token="survey-token",
        prompt="object",
        clock=clock,
        sleep=clock.sleep,
        idle_timeout_s=IDLE_S,
    )
    return Station(control, clock)


STATIONS: list[Callable[[], Station]] = [a_stub_station, a_modal_station]


@pytest.fixture(params=STATIONS, ids=["stub", "modal"])
def station(request: pytest.FixtureRequest) -> Station:
    factory: Callable[[], Station] = request.param
    return factory()


def test_a_new_station_is_off_and_holds_no_gpu(station: Station) -> None:
    # Given a station nobody has used
    # When its status is read
    status = station.control.status()

    # Then it is off, with no container, and reports its idle timeout
    assert (status.state, status.containers, status.idle_timeout_s) == (
        StationState.OFF,
        0,
        IDLE_S,
    )


def test_starting_brings_the_station_up_on_one_container(station: Station) -> None:
    # Given an off station
    # When it is started
    status = station.control.start()

    # Then it is ready on one container
    assert (status.state, status.containers) == (StationState.READY, 1)


def test_starting_a_ready_station_again_leaves_it_ready(station: Station) -> None:
    # Given a ready station
    station.control.start()

    # When it is started again
    status = station.control.start()

    # Then it is still ready on the same one container
    assert (status.state, status.containers) == (StationState.READY, 1)


def test_stopping_takes_the_station_down(station: Station) -> None:
    # Given a ready station
    station.control.start()

    # When it is stopped
    status = station.control.stop()

    # Then it is off and holds no container
    assert (status.state, status.containers) == (StationState.OFF, 0)


def test_stopping_an_off_station_leaves_it_off(station: Station) -> None:
    # Given an off station
    # When it is stopped
    status = station.control.stop()

    # Then nothing changes
    assert (status.state, status.containers) == (StationState.OFF, 0)


def test_the_first_sam_frame_starts_the_station_and_is_segmented_there(station: Station) -> None:
    # Given the SAM detector the agent's workspace is given, before the station is up
    detector = station.control.detector()
    detector.reset("debris")

    # When the first frame is tracked
    detections = detector.track(a_frame())

    # Then the station came up for it and segmented the frame for the prompt
    assert station.control.status().state == StationState.READY
    assert labels(detections) == ["debris"]


def test_the_station_stays_up_within_the_idle_timeout(station: Station) -> None:
    # Given a station that segmented a frame
    detector = station.control.detector()
    detector.track(a_frame())

    # When a second short of the idle timeout passes
    station.clock.advance(IDLE_S - 1)

    # Then it is still up, and says how long it has been idle
    status = station.control.check_idle()
    assert (status.state, status.idle_for_s) == (StationState.READY, IDLE_S - 1)


def test_the_station_goes_down_once_the_idle_timeout_passes_after_the_last_frame(
    station: Station,
) -> None:
    # Given a station that segmented a frame
    detector = station.control.detector()
    detector.track(a_frame())

    # When the idle timeout passes with no further frame
    station.clock.advance(IDLE_S)

    # Then the idle check takes it down
    status = station.control.check_idle()
    assert (status.state, status.containers) == (StationState.OFF, 0)


def test_each_frame_restarts_the_idle_timeout(station: Station) -> None:
    # Given a station that segmented a frame, and another just before the timeout
    detector = station.control.detector()
    detector.track(a_frame(1))
    station.clock.advance(IDLE_S - 10)
    detector.track(a_frame(2))

    # When the timeout passes since the first frame, but not since the second
    station.clock.advance(20)

    # Then it is still up
    assert station.control.check_idle().state == StationState.READY


def test_a_stopped_station_comes_back_on_the_next_frame(station: Station) -> None:
    # Given a station that was used and then stopped
    detector = station.control.detector()
    detector.track(a_frame(1))
    station.control.stop()

    # When the next frame is tracked
    detections = detector.track(a_frame(2))

    # Then the station is up again and segmented it
    assert station.control.status().state == StationState.READY
    assert len(detections) == 1


class FlakyStation(StubStationControl):
    def __init__(self) -> None:
        super().__init__(clock=FakeClock())
        self.checks = 0

    def check_idle(self) -> StationStatus:
        self.checks += 1
        if self.checks == 1:
            raise ConnectionError("Modal API blip")
        return super().check_idle()


def test_an_idle_check_that_fails_once_does_not_stop_the_idle_ticker() -> None:
    # Given a station whose first idle check fails, as a Modal API call can
    station = FlakyStation()
    ticker = IdleTicker(station)

    # When the ticker ticks twice
    ticker.tick()
    ticker.tick()

    # Then the failure was absorbed and the next check still ran
    assert station.checks == 2
