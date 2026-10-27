from collections.abc import AsyncIterable

import pytest

from surmap.slam.base import FrameResult
from surmap.survey.cm5_server import stream_survey
from surmap.survey.object_points import InMemoryObjectPointSource
from surmap.survey.v1 import survey_pb2
from surmap.types import ObjectPoints, Pose, StereoFramePair, Vec3


class FakeSlam:
    """Returns configured static points per frame, at a fixed pose."""

    def __init__(self, points: dict[int, tuple[Vec3, ...]], posed: bool = True) -> None:
        self._points = points
        self._posed = posed

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        pose = Pose(Vec3(0.0, 0.0, 0.0)) if self._posed else None
        return FrameResult(frame.frame_id, frame.t_ns, pose, self._points.get(frame.frame_id, ()))

    def trajectory(self) -> list[Pose]:
        return []

    def close(self) -> None:
        pass


async def as_stream(
    requests: list[survey_pb2.Cm5Request],
) -> AsyncIterable[survey_pb2.Cm5Request]:
    for request in requests:
        yield request


async def collect(
    requests: list[survey_pb2.Cm5Request],
    slam: FakeSlam,
    objects: InMemoryObjectPointSource | None = None,
) -> list[survey_pb2.Cm5Response]:
    return [
        response
        async for response in stream_survey(
            as_stream(requests), slam, objects or InMemoryObjectPointSource()
        )
    ]


def a_config(video_channels: list[int] | None = None) -> survey_pb2.Cm5Request:
    return survey_pb2.Cm5Request(
        config=survey_pb2.Cm5StreamConfig(
            calibration=survey_pb2.StereoCalibration(calibration_id="cal-1", baseline_m=0.12),
            video_channels=video_channels or [],
        )
    )


def a_frame(frame_id: int, channel: int) -> survey_pb2.Cm5Request:
    return survey_pb2.Cm5Request(
        frame=survey_pb2.RawVideoFrame(
            frame_id=frame_id,
            t_ns=frame_id * 1_000_000,
            channel=channel,
            width=640,
            height=480,
            encoding=survey_pb2.FRAME_ENCODING_MJPEG,
            data=b"frame-bytes",
        )
    )


def a_pair(frame_id: int) -> list[survey_pb2.Cm5Request]:
    return [a_frame(frame_id, 0), a_frame(frame_id, 1)]


async def test_scene_points_stream_once_and_are_not_resent_at_the_same_position() -> None:
    # Given two pairs that both see the same static point, plus one new point
    slam = FakeSlam({1: (Vec3(1.0, 2.0, 3.0),), 2: (Vec3(1.0, 2.0, 3.0), Vec3(4.0, 5.0, 6.0))})

    # When the pairs stream through
    responses = await collect([a_config(), *a_pair(1), *a_pair(2)], slam)

    # Then frame 1 sends the point and frame 2 sends only the newly spawned one
    batches = [r.points for r in responses]
    assert [(b.designation, b.frame_id, len(b.points)) for b in batches] == [(1, 1, 1), (1, 2, 1)]
    assert (batches[1].points[0].x, batches[1].points[0].y) == (4.0, 5.0)


async def test_object_points_stream_under_their_own_designation() -> None:
    # Given track 7 seen in pair 1 at one point
    objects = InMemoryObjectPointSource(
        (ObjectPoints(7, 1, 1_000_000, (Vec3(7.0, 8.0, 9.0),), Vec3(7.0, 8.0, 9.0)),)
    )

    responses = await collect([a_config(), *a_pair(1)], FakeSlam({}), objects)

    # Then the scene stays silent and the object batch takes designation 107
    assert [(r.points.designation, len(r.points.points)) for r in responses] == [(107, 1)]


async def test_only_the_requested_video_channels_are_echoed() -> None:
    # Given the requester asked for the left channel only
    responses = await collect([a_config(video_channels=[0]), *a_pair(1)], FakeSlam({}))

    # Then exactly the left frames come back, under designation 2
    videos = [r.video for r in responses if r.HasField("video")]
    assert [(v.designation, v.frame.channel) for v in videos] == [(2, 0)]


async def test_a_frame_whose_pair_never_completes_produces_no_points() -> None:
    slam = FakeSlam({1: (Vec3(1.0, 2.0, 3.0),)})
    responses = await collect([a_config(), a_frame(1, 0)], slam)
    assert responses == []


async def test_an_unposed_pair_places_no_points_in_the_map() -> None:
    # Given RTAB-Map has no pose yet for the pair
    slam = FakeSlam({1: (Vec3(1.0, 2.0, 3.0),)}, posed=False)

    # Then nothing is streamed — never place points with a guessed pose
    responses = await collect([a_config(), *a_pair(1)], slam)
    assert responses == []


async def test_a_stream_that_opens_with_a_frame_is_rejected() -> None:
    with pytest.raises(ValueError, match="config"):
        await collect([a_frame(1, 0)], FakeSlam({}))
