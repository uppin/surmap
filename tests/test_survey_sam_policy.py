import asyncio

from surmap.survey.sam import (
    AnalysisGate,
    AnalysisMode,
    InMemorySamDetector,
    RawFrame,
    SamDetection,
)


def a_frame(frame_id: int = 42) -> RawFrame:
    return RawFrame(frame_id, 1_000_000, 0, 640, 480, "mjpeg", b"frame-bytes")


def a_detection() -> SamDetection:
    return SamDetection("car", 0.9, (0.0, 0.0, 10.0, 10.0), ((1.0, 1.0), (2.0, 1.0)), 7)


async def test_the_fake_detector_returns_its_configured_detections() -> None:
    # Given a detector configured with one car detection
    detector = InMemorySamDetector((a_detection(),))

    # When a frame is analyzed
    detections = await detector.detect(a_frame())

    # Then that detection comes back and the frame was seen
    assert detections == (a_detection(),)
    assert detector.frames == [a_frame()]


async def test_every_frame_mode_waits_for_the_analysis_in_flight() -> None:
    # Given one analysis holding the gate
    gate = AnalysisGate(AnalysisMode.EVERY_FRAME)
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    admitted: list[bool] = []

    async def hold() -> None:
        first_entered.set()
        async with gate.slot() as ok:
            admitted.append(ok)
            await release_first.wait()

    async def follow() -> None:
        async with gate.slot() as ok:
            admitted.append(ok)

    # When a second frame arrives while the first is still analyzing
    first = asyncio.create_task(hold())
    await first_entered.wait()
    second = asyncio.create_task(follow())
    for _ in range(5):
        await asyncio.sleep(0)

    # Then it has not been admitted yet — it queues instead of dropping
    assert admitted == [True]
    release_first.set()
    await first
    await second
    assert admitted == [True, True]
    assert gate.dropped == 0


async def test_best_effort_mode_drops_a_frame_that_arrives_while_busy() -> None:
    # Given one analysis holding the gate
    gate = AnalysisGate(AnalysisMode.BEST_EFFORT_DROP)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold() -> None:
        entered.set()
        async with gate.slot():
            await release.wait()

    holder = asyncio.create_task(hold())
    await entered.wait()
    for _ in range(5):
        await asyncio.sleep(0)

    # When another frame arrives before the detector is free
    # Then it is refused at once and the drop is counted
    async with gate.slot() as admitted:
        assert admitted is False
    assert gate.dropped == 1

    release.set()
    await holder


async def test_best_effort_mode_admits_a_frame_when_the_detector_is_free() -> None:
    gate = AnalysisGate(AnalysisMode.BEST_EFFORT_DROP)
    async with gate.slot() as admitted:
        assert admitted is True
    assert gate.dropped == 0
