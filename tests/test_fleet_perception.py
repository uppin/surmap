"""Only the active drone is mapped and segmented, each drone into its own map.

`FleetPerception` is one bridge connection from a fleet page: each pair goes to its drone's own
RTAB-Map backend and segmentation run (fakes from `tests.fleet_perception_fakes`), a drone whose
frames stop keeps its map, and closing the page finishes every drone. Below it, the
`SamSegmentationSink` over the station's `SamDetector`, and the `PerceptionRegistry` the
`drone_map_status` tool reads.
"""

from __future__ import annotations

import io
import threading

import pytest
from PIL import Image

from surmap.simulation.bevy_wire import BevyWireError, BridgeStatus
from surmap.simulation.fleet.perception import (
    MAX_DRONE_SESSIONS,
    DroneCounts,
    PerceptionRegistry,
    SamSegmentationSink,
)
from surmap.survey.sam import InMemorySamDetector, RawFrame, SamDetection
from tests.fleet_perception_fakes import (
    HELLO,
    LEFT,
    NE_D1,
    NE_D2,
    PAIR,
    PAIR_DRONE,
    ROOF_D1,
    SCENARIO,
    SW_D1,
    SW_D2,
    a_pair,
    a_perception,
    an_open_perception,
    blocks,
)

A_PERSON = SamDetection("person", 0.9, (1.0, 0.0, 3.0, 2.0))
A_SECOND_PERSON = SamDetection("person", 0.8, (0.0, 0.0, 1.0, 1.0))


def a_left_frame(frame_id: int) -> RawFrame:
    return RawFrame(
        frame_id=frame_id,
        t_ns=frame_id * 100_000_000,
        channel=0,
        width=4,
        height=2,
        encoding="gray8",
        data=LEFT,
    )


class HeldDetector:
    """A `SamDetector` that holds each frame until released: the detector falling behind."""

    def __init__(self) -> None:
        self.frames: list[int] = []
        self.started = threading.Event()
        self.release = threading.Event()

    async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        self.frames.append(frame.frame_id)
        self.started.set()
        self.release.wait(timeout=10)
        return (A_PERSON,)

    def holding_its_first_frame(self) -> HeldDetector:
        """Waits until the detector has started on a frame (10 s at most)."""
        self.started.wait(timeout=10)
        return self


# ---- acceptance: one map per drone, only the processed drone's frames -------------------------


def test_two_drones_frames_go_only_to_their_own_map() -> None:
    # Given a fleet page connected for quake-fleet
    rig = an_open_perception()

    # When nest-sw-d1 streams three frames, nest-ne-d1 two, then nest-sw-d1 one more
    rig.streams(*blocks((SW_D1, 3), (NE_D1, 2), (SW_D1, 1)))

    # Then two maps were built, each holding only its own drone's frames
    assert [backend.frame_ids for backend in rig.backends.built] == [[1, 2, 3, 6], [4, 5]]


def test_a_drone_switched_back_continues_in_the_same_map() -> None:
    # Given nest-sw-d1 streamed two frames before the agent switched to nest-ne-d1
    rig = an_open_perception()
    rig.streams(*blocks((SW_D1, 2), (NE_D1, 2)))
    first_map = rig.backends.of_frame(1)

    # When the agent switches back and nest-sw-d1 streams two more
    statuses = rig.streams(a_pair(5, SW_D1), a_pair(6, SW_D1))

    # Then they go into the map it started, whose counts continue from two
    assert rig.backends.of_frame(6) is first_map
    assert [(s.drone_id, s.frames, s.keyframes) for s in statuses] == [
        (SW_D1, 3, 3),
        (SW_D1, 4, 4),
    ]


def test_segmentation_runs_only_on_the_processed_drones_left_frames() -> None:
    # Given a fleet page connected for quake-fleet
    rig = an_open_perception()

    # When nest-sw-d1 streams two frames and nest-ne-d1 one
    rig.streams(*blocks((SW_D1, 2), (NE_D1, 1)))

    # Then each drone's segmentation saw only its own frames, and only their left image
    assert rig.sinks.seen() == {SW_D1: [(1, 0, LEFT), (2, 0, LEFT)], NE_D1: [(3, 0, LEFT)]}


def test_a_frame_without_a_drone_id_is_processed_as_before() -> None:
    # Given a page without a fleet that sent the golden hello
    rig = a_perception()
    rig.streams(HELLO)

    # When it sends the golden pair, which names no drone
    (status,) = rig.streams(PAIR)

    # Then one map processes it as the default drone, and the reply is the single-drone status
    assert [backend.frame_ids for backend in rig.backends.built] == [[7]]
    assert status == BridgeStatus(frames=1, posed=1, lost=False, keyframes=1, dropped=0)
    assert [counts.drone_id for counts in rig.perception.counts()] == ["default"]


def test_a_fifth_drone_is_refused_and_the_first_four_keep_working() -> None:
    # Given four drones each streamed a frame, filling the session limit
    rig = an_open_perception()
    rig.streams(*blocks((SW_D1, 1), (SW_D2, 1), (NE_D1, 1), (NE_D2, 1)))

    # When a fifth drone streams, then nest-sw-d1 again
    refused, resumed = rig.streams(a_pair(5, ROOF_D1), a_pair(6, SW_D1))

    # Then the fifth is refused naming the limit, no map is built for it, and nest-sw-d1 maps on
    assert refused.error == "drone session limit (4) reached; nest-roof-d1 not processed"
    assert len(rig.backends.built) == MAX_DRONE_SESSIONS
    assert (resumed.drone_id, resumed.frames, resumed.error) == (SW_D1, 2, None)


def test_closing_the_page_finishes_every_drone_session() -> None:
    # Given three drones streamed, the last of them twice
    rig = an_open_perception()
    rig.streams(*blocks((SW_D1, 1), (NE_D1, 1), (SW_D2, 2)))

    # When the page closes
    rig.perception.close()

    # Then every map is closed, every capture finished and every segmentation closed, by drone id
    assert rig.events == [
        "backend closed after frame 2",
        "segmentation of nest-ne-d1 closed",
        "capture of nest-ne-d1 finished",
        "backend closed after frame 1",
        "segmentation of nest-sw-d1 closed",
        "capture of nest-sw-d1 finished",
        "backend closed after frame 4",
        "segmentation of nest-sw-d2 closed",
        "capture of nest-sw-d2 finished",
    ]


# ---- the router's other answers ---------------------------------------------------------------


def test_a_pair_before_any_hello_is_refused() -> None:
    # Given a connection that has received nothing
    rig = a_perception()

    # When a drone's pair arrives first, Then the wire error is raised
    with pytest.raises(BevyWireError):
        rig.streams(a_pair(1, SW_D1))


def test_each_drone_s_map_is_built_from_the_hello_calibration() -> None:
    # Given a fleet page connected with the golden 640x480 camera
    rig = an_open_perception()

    # When two drones stream
    rig.streams(*blocks((SW_D1, 1), (NE_D1, 1)))

    # Then both maps were built at the hello's size
    assert rig.backends.calibrations == [(640, 480), (640, 480)]


def test_the_status_names_the_drone_its_frame_came_from() -> None:
    # Given a fleet page connected for quake-fleet
    rig = an_open_perception()

    # When nest-sw-d1's golden pair arrives
    (status,) = rig.streams(PAIR_DRONE)

    # Then the reply is that drone's map status
    assert status == BridgeStatus(
        frames=1, posed=1, lost=False, keyframes=1, dropped=0, drone_id=SW_D1
    )


def test_the_hello_status_counts_nothing_yet() -> None:
    # Given a connection that has received nothing
    rig = a_perception()

    # When the fleet page's hello arrives
    (status,) = rig.streams(HELLO)

    # Then the reply is an empty status, and no map exists yet
    assert status == BridgeStatus(frames=0, posed=0, lost=False, keyframes=0, dropped=0)
    assert rig.backends.built == []


def test_the_processing_drone_is_the_one_whose_frame_came_last() -> None:
    # Given a fleet page connected for quake-fleet
    rig = an_open_perception()

    # When nest-sw-d1 streams, then nest-ne-d1
    rig.streams(*blocks((SW_D1, 2), (NE_D1, 1)))

    # Then nest-ne-d1 is the drone being processed
    assert rig.perception.processing() == NE_D1


def test_no_drone_is_processing_before_any_frame() -> None:
    # Given a fleet page that has only said hello
    rig = an_open_perception()

    # When the processing drone is asked for, Then there is none
    assert rig.perception.processing() is None


def test_a_refused_drone_does_not_become_the_processing_drone() -> None:
    # Given four drones streamed, nest-ne-d2 last
    rig = an_open_perception()
    rig.streams(*blocks((SW_D1, 1), (SW_D2, 1), (NE_D1, 1), (NE_D2, 1)))

    # When a fifth drone is refused
    rig.streams(a_pair(5, ROOF_D1))

    # Then nest-ne-d2 is still the drone being processed
    assert rig.perception.processing() == NE_D2


def test_every_drone_s_counts_are_reported_in_drone_id_order() -> None:
    # Given nest-sw-d1 streamed two frames, then nest-ne-d1 one
    rig = an_open_perception()
    rig.streams(*blocks((SW_D1, 2), (NE_D1, 1)))

    # When the connection's counts are read
    counts = rig.perception.counts()

    # Then each drone has its own frames, segmentation and last frame time
    assert counts == (
        DroneCounts(
            drone_id=NE_D1,
            frames=1,
            posed=1,
            lost=0,
            keyframes=1,
            dropped=0,
            segmented_frames=1,
            detections=2,
            processing=True,
            last_t_ns=300_000_000,
        ),
        DroneCounts(
            drone_id=SW_D1,
            frames=2,
            posed=2,
            lost=0,
            keyframes=2,
            dropped=0,
            segmented_frames=2,
            detections=4,
            processing=False,
            last_t_ns=200_000_000,
        ),
    )


def test_each_drone_s_capture_records_only_its_own_pairs() -> None:
    # Given a fleet page connected for quake-fleet
    rig = an_open_perception()

    # When nest-sw-d1 streams two frames and nest-ne-d1 one
    rig.streams(*blocks((SW_D1, 2), (NE_D1, 1)))

    # Then each drone's capture holds its own pairs
    assert rig.recorders.recorded() == {SW_D1: [1, 2], NE_D1: [3]}


def test_a_drone_s_left_frame_reaches_its_map_as_a_png() -> None:
    # Given a fleet page connected for quake-fleet
    rig = an_open_perception()

    # When nest-sw-d1's golden pair arrives
    rig.streams(PAIR_DRONE)

    # Then its map receives the left eye as a 4x2 grey PNG of the pair's bytes
    frame = rig.backends.built[0].frames[0]
    with Image.open(io.BytesIO(frame.left_data)) as left:
        assert (left.size, list(left.getdata())) == ((4, 2), list(range(8)))


# ---- the registry the status tool reads -------------------------------------------------------


def test_a_fleet_page_s_hello_registers_it_under_its_scenario() -> None:
    # Given a registry and a connection over it
    registry = PerceptionRegistry()
    rig = a_perception(registry)

    # When the page's hello names quake-fleet
    rig.opened(SCENARIO)

    # Then the scenario's page is that connection
    assert registry.perception(SCENARIO) is rig.perception


def test_a_hello_without_a_scenario_registers_nothing() -> None:
    # Given a registry and a connection over it
    registry = PerceptionRegistry()
    rig = a_perception(registry)

    # When the golden hello, which names no scenario, arrives
    rig.streams(HELLO)

    # Then no scenario has a page
    assert registry.perception(SCENARIO) is None


def test_closing_the_page_unregisters_it() -> None:
    # Given a page connected for quake-fleet
    registry = PerceptionRegistry()
    rig = an_open_perception(registry)

    # When it closes
    rig.perception.close()

    # Then the scenario has no page any more
    assert registry.perception(SCENARIO) is None


def test_a_later_page_for_the_scenario_replaces_the_earlier_one() -> None:
    # Given a page connected for quake-fleet
    registry = PerceptionRegistry()
    earlier = an_open_perception(registry)

    # When a second page connects for it and the first then closes
    later = an_open_perception(registry)
    earlier.perception.close()

    # Then the scenario's page is the later one
    assert registry.perception(SCENARIO) is later.perception


# ---- the SAM segmentation sink ----------------------------------------------------------------


def test_the_sam_sink_segments_each_left_frame_and_counts_its_detections() -> None:
    # Given a sink over a detector that finds two people in every frame
    detector = InMemorySamDetector((A_PERSON, A_SECOND_PERSON))
    sink = SamSegmentationSink(detector)

    # When two left frames are submitted and the sink is closed
    sink.submit(a_left_frame(1))
    sink.submit(a_left_frame(2))
    sink.close()

    # Then the detector saw both, and the sink counted two frames and four detections
    assert [frame.frame_id for frame in detector.frames] == [1, 2]
    assert (sink.segmented_frames, sink.detections, sink.dropped_frames) == (2, 4, 0)


def test_the_sam_sink_drops_the_oldest_frame_when_the_detector_falls_behind() -> None:
    # Given a sink whose detector is still holding frame 1
    detector = HeldDetector()
    sink = SamSegmentationSink(detector)
    sink.submit(a_left_frame(1))
    detector.holding_its_first_frame()

    # When three more frames arrive before it is released, and the sink is closed
    sink.submit(a_left_frame(2))
    sink.submit(a_left_frame(3))
    sink.submit(a_left_frame(4))
    detector.release.set()
    sink.close()

    # Then frame 2 was dropped and the two newest were segmented after frame 1
    assert detector.frames == [1, 3, 4]
    assert (sink.segmented_frames, sink.dropped_frames) == (3, 1)
