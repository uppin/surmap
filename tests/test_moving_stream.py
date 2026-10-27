"""Handler-level test for the assembled moving-areas stream (n5).

Fake stereo + batch fake SLAM in, areas with verdicts and
flush-time snapshots out: the whole stages 1-6 chain, exercised
through `stream_moving_areas` itself.
"""

from __future__ import annotations

from collections.abc import AsyncIterable

from surmap.moving.placement import AREA_TRACK_ID_BASE
from surmap.slam.base import FrameResult
from surmap.survey.cm5_server import stream_moving_areas
from surmap.survey.v1 import survey_pb2
from surmap.types import Pose, StereoFramePair, Vec3

STATIC = tuple(Vec3((i % 8) * 0.05, (i // 8) * 0.05, 10.0) for i in range(40))


def _mover(frame_index: int) -> tuple[Vec3, ...]:
    return tuple(
        Vec3(0.5 * frame_index + (j % 8) * 0.05, 5.0 + (j // 8) * 0.05, 10.0) for j in range(40)
    )


class FakeStereo:
    """Returns the static grid plus a mover cluster moving in +x."""

    def __init__(self) -> None:
        self.calls = 0

    def reconstruct(self, left: object, right: object, rig: object) -> tuple[Vec3, ...]:
        index = self.calls
        self.calls += 1
        if index == 0:
            return STATIC
        return STATIC + _mover(index)


class BatchSlam:
    """Poses only at flush (like the RTAB sidecar)."""

    def __init__(self) -> None:
        self._frames: list[StereoFramePair] = []

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self._frames.append(frame)
        return FrameResult(frame.frame_id, frame.t_ns, None, ())

    def flush(self) -> list[FrameResult]:
        return [
            FrameResult(f.frame_id, f.t_ns, Pose(Vec3(0.0, 0.0, 0.0)), STATIC) for f in self._frames
        ]

    def trajectory(self) -> list[Pose]:
        return []

    def close(self) -> None:
        pass


def _config() -> survey_pb2.Cm5Request:
    return survey_pb2.Cm5Request(
        config=survey_pb2.Cm5StreamConfig(
            calibration=survey_pb2.StereoCalibration(
                calibration_id="cal-1",
                focal_length_px=100.0,
                baseline_m=0.5,
            ),
        )
    )


def _frame(frame_id: int, channel: int) -> survey_pb2.Cm5Request:
    return survey_pb2.Cm5Request(
        frame=survey_pb2.RawVideoFrame(
            frame_id=frame_id,
            t_ns=frame_id * 200_000_000,
            channel=channel,
            width=64,
            height=48,
            encoding=survey_pb2.FRAME_ENCODING_MJPEG,
            data=b"frame",
        )
    )


async def _stream(
    requests: list[survey_pb2.Cm5Request],
) -> AsyncIterable[survey_pb2.Cm5Request]:
    for request in requests:
        yield request


async def test_moving_stream_graduates_and_snapshots_at_flush() -> None:
    requests = [_config()]
    for frame_id in range(9):
        requests += [_frame(frame_id, 0), _frame(frame_id, 1)]
    responses = [
        response
        async for response in stream_moving_areas(
            _stream(requests), stereo=FakeStereo(), slam=BatchSlam()
        )
    ]
    areas = [r.area for r in responses if r.HasField("area")]
    snapshots = [r.snapshot for r in responses if r.HasField("snapshot")]
    assert areas, "expected live areas"
    assert any(a.verdict == survey_pb2.MOVING_VERDICT_RIGID_MOVER for a in areas)
    assert snapshots, "expected flush-time snapshots for the graduated track"
    snapshot = snapshots[0]
    assert snapshot.object_track_id >= AREA_TRACK_ID_BASE
    assert snapshot.verdict == survey_pb2.MOVING_VERDICT_RIGID_MOVER
    assert len(snapshot.keypoints) > 0
    assert snapshot.frame_id >= 6
