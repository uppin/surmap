"""A CM5 survey stream keeps the event loop free while its backends work.

The CM5 serves every call of a client over one WebSocket on one event loop: the survey stream,
region queries, detections and the keepalive. SLAM, stereo and object-point work is blocking, so
it runs off the loop; a slow pair must not stall the other calls.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterable

from surmap.slam.base import FrameResult
from surmap.survey.cm5_server import stream_survey
from surmap.survey.object_points import InMemoryObjectPointSource
from surmap.survey.stereo import StereoRig
from surmap.survey.v1 import survey_pb2
from surmap.types import ObjectPoints, Pose, StereoFramePair, Vec3

BLOCK_S = 0.4
TICK_S = 0.02


class SlowSlam:
    """Blocks its caller for `BLOCK_S` per pair, as a backend writing to a full pipe does."""

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        time.sleep(BLOCK_S)
        return FrameResult(frame.frame_id, frame.t_ns, Pose(Vec3(0.0, 0.0, 0.0)))

    def trajectory(self) -> list[Pose]:
        return []

    def close(self) -> None:
        pass


class SlowObjects(InMemoryObjectPointSource):
    """Blocks its caller for `BLOCK_S` per pair, as a detector lifting object points does."""

    def points_for_pair(
        self, pair: StereoFramePair, pose: Pose | None, rig: StereoRig | None = None
    ) -> tuple[ObjectPoints, ...]:
        time.sleep(BLOCK_S)
        return ()


def a_pair(frame_id: int) -> list[survey_pb2.Cm5Request]:
    return [
        survey_pb2.Cm5Request(
            frame=survey_pb2.RawVideoFrame(
                frame_id=frame_id,
                t_ns=frame_id * 1_000_000,
                channel=channel,
                width=640,
                height=480,
                encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                data=b"f",
            )
        )
        for channel in (0, 1)
    ]


async def one_pair() -> AsyncIterable[survey_pb2.Cm5Request]:
    yield survey_pb2.Cm5Request(
        config=survey_pb2.Cm5StreamConfig(
            calibration=survey_pb2.StereoCalibration(calibration_id="cal-1")
        )
    )
    for request in a_pair(1):
        yield request


async def ticks_while_serving(slam: object, objects: InMemoryObjectPointSource) -> int:
    """How many `TICK_S` ticks another coroutine got while the stream was served."""
    ticks = 0
    serving = True

    async def ticker() -> None:
        nonlocal ticks
        while serving:
            await asyncio.sleep(TICK_S)
            ticks += 1

    ticking = asyncio.create_task(ticker())
    _ = [r async for r in stream_survey(one_pair(), slam, objects)]  # type: ignore[arg-type]
    serving = False
    await ticking
    return ticks


async def test_a_slow_slam_backend_does_not_stall_the_event_loop() -> None:
    # Given a SLAM backend that blocks for 0.4 s on a pair
    # When a stream with one pair is served while another coroutine ticks every 20 ms
    ticks = await ticks_while_serving(SlowSlam(), InMemoryObjectPointSource())

    # Then the other coroutine kept running through the backend's work
    assert ticks >= (BLOCK_S / TICK_S) / 2


async def test_slow_object_point_lifting_does_not_stall_the_event_loop() -> None:
    # Given an object-point source that blocks for 0.4 s on a pair
    class PosedSlam(SlowSlam):
        def process_frame(self, frame: StereoFramePair) -> FrameResult:
            return FrameResult(frame.frame_id, frame.t_ns, Pose(Vec3(0.0, 0.0, 0.0)))

    # When a stream with one pair is served while another coroutine ticks every 20 ms
    ticks = await ticks_while_serving(PosedSlam(), SlowObjects())

    # Then the other coroutine kept running through the lifting
    assert ticks >= (BLOCK_S / TICK_S) / 2
