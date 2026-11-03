"""GPS on the CM5 survey stream: a simulator sends fixes between frames, the CM5 anchors each.

A `GpsFix` on `Cm5Request` is answered with a `GpsAnchorOut` on `Cm5Response`: the fix itself,
plus the frame id and map position of the posed frame nearest to it in time — within 0.5 s, or
no position at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable

from surmap.slam.base import FrameResult
from surmap.slam.stream_protocol import OdomUpdate
from surmap.survey.cm5_server import stream_survey
from surmap.survey.object_points import InMemoryObjectPointSource
from surmap.survey.v1 import survey_pb2
from surmap.types import Pose, StereoFramePair, Vec3

MS = 1_000_000


class SlamAlongX:
    """Poses frame `n` at x = n metres."""

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        return FrameResult(frame.frame_id, frame.t_ns, Pose(Vec3(float(frame.frame_id), 0.0, 0.0)))

    def trajectory(self) -> list[Pose]:
        return []

    def close(self) -> None:
        pass


def a_config() -> survey_pb2.Cm5Request:
    return survey_pb2.Cm5Request(
        config=survey_pb2.Cm5StreamConfig(
            calibration=survey_pb2.StereoCalibration(calibration_id="sim")
        )
    )


def a_pair(frame_id: int, t_ns: int) -> list[survey_pb2.Cm5Request]:
    return [
        survey_pb2.Cm5Request(
            frame=survey_pb2.RawVideoFrame(
                frame_id=frame_id,
                t_ns=t_ns,
                channel=channel,
                width=640,
                height=480,
                encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                data=b"f",
            )
        )
        for channel in (0, 1)
    ]


def a_fix(t_ns: int) -> survey_pb2.Cm5Request:
    return survey_pb2.Cm5Request(
        gps=survey_pb2.GpsFix(t_ns=t_ns, lat=47.3769, lon=8.5417, alt_m=420.5, accuracy_m=1.5)
    )


async def as_stream(
    requests: list[survey_pb2.Cm5Request],
) -> AsyncIterable[survey_pb2.Cm5Request]:
    for request in requests:
        yield request


async def anchors_of(requests: list[survey_pb2.Cm5Request]) -> list[survey_pb2.GpsAnchorOut]:
    return [
        response.gps_anchor
        async for response in stream_survey(
            as_stream(requests), SlamAlongX(), InMemoryObjectPointSource()
        )
        if response.WhichOneof("kind") == "gps_anchor"
    ]


async def test_a_fix_after_posed_frames_is_anchored_to_the_frame_nearest_in_time() -> None:
    # Given frames 1 and 2 posed at x = 1 m and x = 2 m, 100 ms apart
    requests = [a_config(), *a_pair(1, 1_000 * MS), *a_pair(2, 1_100 * MS)]

    # When a fix taken at 1 090 ms arrives
    (anchor,) = await anchors_of([*requests, a_fix(1_090 * MS)])

    # Then it is anchored to frame 2's map position, and repeats the fix
    assert (anchor.frame_id, anchor.map_position.x) == (2, 2.0)
    assert (anchor.fix.lat, anchor.fix.lon, anchor.fix.alt_m) == (47.3769, 8.5417, 420.5)


async def test_a_fix_with_no_pose_within_half_a_second_has_no_map_position() -> None:
    # Given one frame posed at 1 000 ms
    requests = [a_config(), *a_pair(1, 1_000 * MS)]

    # When a fix taken 600 ms later arrives
    (anchor,) = await anchors_of([*requests, a_fix(1_600 * MS)])

    # Then the fix is acknowledged without a map position
    assert anchor.HasField("map_position") is False
    assert anchor.fix.t_ns == 1_600 * MS


async def test_a_fix_before_any_frame_is_acknowledged_without_a_map_position() -> None:
    # Given a stream that sends a fix right after its config
    # When the CM5 serves it
    (anchor,) = await anchors_of([a_config(), a_fix(5 * MS)])

    # Then the fix comes back unanchored
    assert anchor.HasField("map_position") is False


async def test_a_fix_mid_stream_adds_only_its_anchor_to_the_output() -> None:
    # Given a pair, a fix, then another pair, on a SLAM that posts no scene points
    requests = [a_config(), *a_pair(1, 1_000 * MS), a_fix(1_050 * MS), *a_pair(2, 1_100 * MS)]

    # When the CM5 serves the stream
    kinds = [
        response.WhichOneof("kind")
        async for response in stream_survey(
            as_stream(requests), SlamAlongX(), InMemoryObjectPointSource()
        )
    ]

    # Then the one response is the fix's anchor
    assert kinds == ["gps_anchor"]


class LiveSlamAlongX:
    """A live backend: a pair's result carries no pose; its odometry (x = frame id metres) lands
    later, once `land(frame_id)` is called, as RTAB-Map's does while it catches up."""

    def __init__(self) -> None:
        self._t_ns: dict[int, int] = {}
        self._landed: set[int] = set()

    def land(self, frame_id: int) -> None:
        self._landed.add(frame_id)

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self._t_ns[frame.frame_id] = frame.t_ns
        return FrameResult(frame.frame_id, frame.t_ns, None)

    def frame_odometry(self, frame_id: int) -> OdomUpdate | None:
        if frame_id not in self._landed:
            return None
        pose = Pose(Vec3(float(frame_id), 0.0, 0.0))
        return OdomUpdate(frame_id, self._t_ns[frame_id], pose, False, 1.0)

    def trajectory(self) -> list[Pose]:
        return []

    def close(self) -> None:
        pass


async def test_a_fix_sent_before_its_frames_pose_lands_is_anchored_once_it_does() -> None:
    # Given a live backend whose pose for frame 1 has not landed when its fix arrives
    slam = LiveSlamAlongX()

    async def requests() -> AsyncIterable[survey_pb2.Cm5Request]:
        yield a_config()
        for request in a_pair(1, 1_000 * MS):
            yield request
        yield a_fix(1_000 * MS)
        slam.land(1)
        for request in a_pair(2, 1_100 * MS):
            yield request

    # When the stream is served
    anchors = [
        response.gps_anchor
        async for response in stream_survey(requests(), slam, InMemoryObjectPointSource())
        if response.WhichOneof("kind") == "gps_anchor"
    ]

    # Then the fix waited for frame 1's pose and was anchored to it
    assert [(a.frame_id, a.map_position.x) for a in anchors] == [(1, 1.0)]


async def test_odometry_landing_while_the_sender_is_idle_is_streamed_without_waiting() -> None:
    # Given a live backend and a sender that sends one pair, then waits for its odometry
    slam = LiveSlamAlongX()
    odometry_seen = asyncio.Event()

    async def requests() -> AsyncIterable[survey_pb2.Cm5Request]:
        yield a_config()
        for request in a_pair(1, 1_000 * MS):
            yield request
        slam.land(1)
        # Nothing more is sent until frame 1's odometry has come back.
        await asyncio.wait_for(odometry_seen.wait(), 5.0)

    # When the stream is served
    kinds: list[str | None] = []
    async for response in stream_survey(requests(), slam, InMemoryObjectPointSource()):
        kinds.append(response.WhichOneof("kind"))
        if response.WhichOneof("kind") == "odom":
            odometry_seen.set()

    # Then the odometry arrived while the sender was idle
    assert kinds == ["odom"]
