import asyncio
from collections.abc import AsyncIterable

import pytest

from surmap.survey.sam import InMemorySamDetector, RawFrame, SamDetection
from surmap.survey.station_server import stream_analysis
from surmap.survey.v1 import survey_pb2


def a_detection() -> SamDetection:
    return SamDetection("car", 0.9, (0.0, 0.0, 10.0, 10.0), ((1.0, 1.0), (2.0, 1.0)), 7)


class SlowDetector:
    """Holds its first analysis until the test releases it."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        self.started.set()
        await self.release.wait()
        return (a_detection(),)


def a_config(mode: int) -> survey_pb2.StationRequest:
    return survey_pb2.StationRequest(
        config=survey_pb2.StationStreamConfig(
            calibration=survey_pb2.StereoCalibration(calibration_id="cal-1", baseline_m=0.12),
            analysis_mode=mode,
        )
    )


def a_frame(frame_id: int) -> survey_pb2.StationRequest:
    return survey_pb2.StationRequest(
        frame=survey_pb2.RawVideoFrame(
            frame_id=frame_id,
            t_ns=frame_id * 1_000_000,
            channel=0,
            width=640,
            height=480,
            encoding=survey_pb2.FRAME_ENCODING_MJPEG,
            data=b"frame-bytes",
        )
    )


async def as_stream(
    requests: list[survey_pb2.StationRequest],
) -> AsyncIterable[survey_pb2.StationRequest]:
    for request in requests:
        yield request


async def collect(
    requests: list[survey_pb2.StationRequest],
    detector: InMemorySamDetector | SlowDetector,
) -> list[survey_pb2.StationResponse]:
    return [response async for response in stream_analysis(as_stream(requests), detector)]


async def test_an_analyzed_frame_is_answered_under_its_assigned_frame_id() -> None:
    # Given a frame the requester numbered 42
    detector = InMemorySamDetector((a_detection(),))

    # When it is analyzed on an every-frame stream
    responses = await collect(
        [a_config(survey_pb2.ANALYSIS_MODE_EVERY_FRAME), a_frame(42)], detector
    )

    # Then the answer repeats 42 and carries the detection vector intact
    (response,) = responses
    detections = response.detections
    assert detections.frame_id == 42
    (detection,) = detections.detections
    assert detection.label == "car"
    assert detection.score == 0.9
    assert detection.track_id == 7
    assert (detection.box.x_max, detection.box.y_max) == (10.0, 10.0)
    assert [(p.x, p.y) for p in detection.mask_polygon] == [(1.0, 1.0), (2.0, 1.0)]


async def test_every_frame_mode_answers_a_burst_in_order() -> None:
    detector = SlowDetector()
    stream = asyncio.create_task(
        collect(
            [a_config(survey_pb2.ANALYSIS_MODE_EVERY_FRAME), a_frame(1), a_frame(2)],
            detector,
        )
    )
    await detector.started.wait()

    # Frames queue behind the analysis in flight instead of dropping
    assert not stream.done()
    detector.release.set()
    responses = await stream
    assert [r.detections.frame_id for r in responses] == [1, 2]


async def test_best_effort_mode_gives_no_answer_for_a_frame_that_arrives_while_busy() -> None:
    detector = SlowDetector()
    stream = asyncio.create_task(
        collect(
            [a_config(survey_pb2.ANALYSIS_MODE_BEST_EFFORT_DROP), a_frame(1), a_frame(2)],
            detector,
        )
    )
    await detector.started.wait()
    for _ in range(5):
        await asyncio.sleep(0)

    # Frame 2 arrived mid-analysis: it is dropped, never answered
    detector.release.set()
    responses = await stream
    assert [r.detections.frame_id for r in responses] == [1]


async def test_a_stream_that_opens_with_a_frame_is_rejected() -> None:
    with pytest.raises(ValueError, match="config"):
        await collect([a_frame(1)], InMemorySamDetector())
