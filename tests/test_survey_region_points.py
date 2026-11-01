"""`Cm5SurveyService.StreamRegionPoints`: SAM polygon in, dense map-frame points out."""

from collections.abc import AsyncIterable
from pathlib import Path
from typing import cast

import pytest

from surmap.rpc.hosts.in_memory import InMemoryHost
from surmap.slam.regions import InMemoryRegionPointSource, RegionPointSource
from surmap.survey.cm5_main import build_description, main, streaming_backend
from surmap.survey.cm5_server import stream_region_points
from surmap.survey.v1 import survey_pb2
from surmap.types import Vec3
from tests.test_demo import CAM0_YAML
from tests.test_slam_streaming import FakeProcess, _hello

SQUARE = ((10.0, 10.0), (50.0, 10.0), (50.0, 50.0), (10.0, 50.0))
OK = survey_pb2.REGION_STATUS_OK


def a_region_query(
    query_id: int = 1,
    frame_id: int = 7,
    channel: int = 0,
    polygon: tuple[tuple[float, float], ...] = SQUARE,
) -> survey_pb2.RegionQuery:
    return survey_pb2.RegionQuery(
        query_id=query_id,
        frame_id=frame_id,
        channel=channel,
        width=376,
        height=240,
        polygon=[survey_pb2.Point2(x=x, y=y) for x, y in polygon],
    )


def points_along_x(count: int, z: float = 3.0) -> tuple[Vec3, ...]:
    return tuple(Vec3(0.01 * index, 0.0, z) for index in range(count))


async def as_stream(
    queries: list[survey_pb2.RegionQuery],
) -> AsyncIterable[survey_pb2.RegionQuery]:
    for query in queries:
        yield query


async def ask(
    queries: list[survey_pb2.RegionQuery],
    source: RegionPointSource | None,
    max_points_per_message: int = 10_000,
) -> list[survey_pb2.RegionPoints]:
    return [
        response
        async for response in stream_region_points(
            as_stream(queries), source, max_points_per_message=max_points_per_message
        )
    ]


def xyz(response: survey_pb2.RegionPoints) -> list[tuple[float, float, float]]:
    return [(point.x, point.y, point.z) for point in response.points]


async def test_a_tracked_frame_answers_with_every_point_in_its_region() -> None:
    # Given a CM5 holding three map-frame points for frame 7's region
    source = InMemoryRegionPointSource({7: points_along_x(3)})

    # When SAM's polygon on frame 7's left image is queried
    responses = await ask([a_region_query(query_id=11)], source)

    # Then one final OK message repeats the query and carries all three points
    assert len(responses) == 1
    answer = responses[0]
    assert (answer.query_id, answer.frame_id, answer.channel) == (11, 7, 0)
    assert answer.status == OK and answer.final
    assert xyz(answer) == [(0.0, 0.0, 3.0), (0.01, 0.0, 3.0), (0.02, 0.0, 3.0)]


async def test_the_channel_sam_segmented_is_passed_to_the_source_and_repeated() -> None:
    # Given a CM5 holding points for frame 7
    source = InMemoryRegionPointSource({7: points_along_x(1)})

    # When the polygon was drawn on the right image
    responses = await ask([a_region_query(channel=1)], source)

    # Then depth is asked for the right channel, and the answer says so
    assert [query.channel for query in source.queries] == [1]
    assert responses[0].channel == 1


async def test_a_large_region_is_chunked_and_only_the_last_chunk_is_final() -> None:
    # Given a region of 25 points and messages of at most 10
    source = InMemoryRegionPointSource({7: points_along_x(25)})

    # When it is queried
    responses = await ask([a_region_query()], source, max_points_per_message=10)

    # Then 10 + 10 + 5 points arrive in order, final only on the last
    assert [len(response.points) for response in responses] == [10, 10, 5]
    assert [response.final for response in responses] == [False, False, True]
    assert [p for response in responses for p in xyz(response)] == [
        (p.x, p.y, p.z) for p in points_along_x(25)
    ]


async def test_each_query_is_answered_from_its_own_frame_never_accumulated() -> None:
    # Given different regions on frames 7 and 8
    source = InMemoryRegionPointSource({7: points_along_x(2, z=3.0), 8: points_along_x(1, z=5.0)})

    # When both are queried on one stream
    responses = await ask([a_region_query(1, frame_id=7), a_region_query(2, frame_id=8)], source)

    # Then the second answer carries only frame 8's point, not frame 7's too
    by_query = {response.query_id: xyz(response) for response in responses}
    assert by_query == {1: [(0.0, 0.0, 3.0), (0.01, 0.0, 3.0)], 2: [(0.0, 0.0, 5.0)]}


async def test_a_frame_the_cm5_no_longer_holds_is_reported_expired() -> None:
    # Given a CM5 holding only frame 7
    source = InMemoryRegionPointSource({7: points_along_x(3)})

    # When frame 3 is queried
    responses = await ask([a_region_query(frame_id=3)], source)

    # Then one final message says the frame expired, with no points
    assert [(r.status, r.final, len(r.points)) for r in responses] == [
        (survey_pb2.REGION_STATUS_FRAME_EXPIRED, True, 0)
    ]


@pytest.mark.parametrize(
    "query",
    [
        a_region_query(channel=2),
        a_region_query(polygon=SQUARE[:2]),
        survey_pb2.RegionQuery(query_id=1, frame_id=7, channel=0, width=0, height=240),
    ],
    ids=["no-such-channel", "two-vertices", "no-image-size"],
)
async def test_an_invalid_query_is_refused_without_asking_for_depth(
    query: survey_pb2.RegionQuery,
) -> None:
    # Given a CM5 that holds frame 7
    source = InMemoryRegionPointSource({7: points_along_x(3)})

    # When an invalid query arrives
    responses = await ask([query], source)

    # Then it is answered INVALID_QUERY and the depth source is never asked
    assert [(r.status, r.final) for r in responses] == [
        (survey_pb2.REGION_STATUS_INVALID_QUERY, True)
    ]
    assert source.queries == []


async def test_a_cm5_without_a_region_source_rejects_the_stream() -> None:
    # Given / When / Then
    with pytest.raises(ValueError, match="no region source configured"):
        await ask([a_region_query()], None)


async def test_the_region_stream_is_mounted_on_the_cm5_survey_service() -> None:
    # Given a CM5 server description with a region source
    source = InMemoryRegionPointSource({7: points_along_x(2)})
    host = InMemoryHost(build_description(use_stereo=False, regions=source), None)
    client = host.client(survey_pb2.DESCRIPTOR.services_by_name["Cm5SurveyService"])

    # When a requester streams one query in-process
    responses = [
        cast("survey_pb2.RegionPoints", message)
        async for message in client.bidi("StreamRegionPoints", as_stream([a_region_query(3)]))
    ]

    # Then the CM5 answers it over the service
    assert [(r.query_id, r.status, len(r.points)) for r in responses] == [(3, OK, 2)]


def test_the_cm5_live_mode_needs_a_calibration_dir() -> None:
    # Given / When / Then the live RTAB-Map mode cannot start uncalibrated
    with pytest.raises(SystemExit):
        main(["--slam-backend", "streaming"])


def test_the_cm5_live_mode_starts_the_streaming_sidecar_at_the_frame_size(
    tmp_path: Path,
) -> None:
    # Given a EuRoC-layout calibration dir
    for camera in ("cam0", "cam1"):
        (tmp_path / "mav0" / camera).mkdir(parents=True)
        (tmp_path / "mav0" / camera / "sensor.yaml").write_text(CAM0_YAML, encoding="utf-8")
    started: list[FakeProcess] = []

    def factory(argv: list[str]) -> FakeProcess:
        started.append(FakeProcess(argv))
        return started[-1]

    # When the CM5's live backend is built for 376 x 240 frames
    backend = streaming_backend(tmp_path, (376, 240), process_factory=factory)
    backend.close()

    # Then the sidecar is told that size, with the camera scaled to it,
    # and the backend serves both poses and regions
    hello = _hello(started[0])
    assert (hello["width"], hello["height"]) == (376, 240)
    assert "resolution: [376, 240]" in str(hello["cam0_yaml"])
    assert isinstance(backend, RegionPointSource)
