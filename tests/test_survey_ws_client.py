"""`SurveyConnection`: one asyncio WebSocket to a CM5 or station server, every survey call on it.

The servers are the real descriptions on a loopback socket, serving Connect on `/connect`; the
client dials once and runs unary, bidi survey, region and analysis calls over that one socket.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.slam.base import FrameResult
from surmap.slam.regions import InMemoryRegionPointSource, RegionQuery, RegionResult
from surmap.survey.cm5_main import build_description as cm5_description
from surmap.survey.sam import InMemorySamDetector, SamDetection
from surmap.survey.station_main import build_description as station_description
from surmap.survey.v1 import survey_pb2
from surmap.survey.ws_client import SurveyConnection, connect_url
from surmap.types import Pose, StereoFramePair, Vec3

TOKEN = "survey-secret"
SQUARE = ((10.0, 10.0), (50.0, 10.0), (50.0, 50.0), (10.0, 50.0))


class _PosedSlam:
    """Every pair is posed at the origin with one scene point."""

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        return FrameResult(
            frame.frame_id, frame.t_ns, Pose(Vec3(0.0, 0.0, 0.0)), (Vec3(1.0, 2.0, 3.0),)
        )

    def trajectory(self) -> list[Pose]:
        return []

    def close(self) -> None:
        pass


@asynccontextmanager
async def serving(
    description: ServerDescription[None], token: str | None = None
) -> AsyncIterator[str]:
    """A real server on an ephemeral loopback port; yields its `ws://` Connect URL."""
    host = HypercornHost(description, None, auth_token=token)
    ports = await host.start()
    try:
        yield f"ws://127.0.0.1:{ports.public}/connect"
    finally:
        await host.stop()


def a_config() -> survey_pb2.Cm5Request:
    return survey_pb2.Cm5Request(
        config=survey_pb2.Cm5StreamConfig(
            calibration=survey_pb2.StereoCalibration(calibration_id="cal-1")
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
            data=b"f",
        )
    )


def a_region_query(query_id: int, frame_id: int) -> survey_pb2.RegionQuery:
    return survey_pb2.RegionQuery(
        query_id=query_id,
        frame_id=frame_id,
        channel=0,
        width=376,
        height=240,
        polygon=[survey_pb2.Point2(x=x, y=y) for x, y in SQUARE],
    )


async def test_the_connection_reports_the_cm5_capabilities() -> None:
    # Given a CM5 server guarded by a token
    async with serving(cm5_description(use_stereo=False), TOKEN) as url:
        # When a connection with the token asks for the CM5 capabilities
        async with SurveyConnection.open(url, token=TOKEN) as connection:
            capabilities = await connection.capabilities("Cm5SurveyService")

    # Then they describe the CM5 build
    assert (capabilities.service, capabilities.slam) == ("cm5", "inmemory")


async def test_a_survey_streams_points_back_while_frames_are_still_being_sent() -> None:
    # Given a CM5 server whose SLAM poses every pair with one scene point
    second_pair_sent = asyncio.Event()
    first_points_seen = asyncio.Event()

    async def frames() -> AsyncIterator[survey_pb2.Cm5Request]:
        yield a_config()
        yield a_frame(1, 0)
        yield a_frame(1, 1)
        await first_points_seen.wait()
        yield a_frame(2, 0)
        yield a_frame(2, 1)
        second_pair_sent.set()

    async with serving(cm5_description(slam=_PosedSlam(), use_stereo=False)) as url:
        async with SurveyConnection.open(url) as connection:
            # When the first pair's points arrive before the second pair is sent
            batches: list[tuple[int, bool]] = []
            async for response in connection.stream_survey(frames()):
                if response.WhichOneof("kind") == "points":
                    batches.append((response.points.frame_id, second_pair_sent.is_set()))
                    first_points_seen.set()

    # Then frame 1's scene batch came back while the stream was still open for frame 2
    assert batches[0] == (1, False)


async def test_region_points_answer_a_frame_held_by_the_same_cm5() -> None:
    # Given a CM5 server holding dense points for frame 7
    regions = InMemoryRegionPointSource({7: (Vec3(0.0, 0.0, 3.0), Vec3(0.01, 0.0, 3.0))})

    async def queries() -> AsyncIterator[survey_pb2.RegionQuery]:
        yield a_region_query(3, 7)

    async with serving(cm5_description(use_stereo=False, regions=regions)) as url:
        # When a connection asks for the region under a polygon on frame 7
        async with SurveyConnection.open(url) as connection:
            responses = [r async for r in connection.stream_region_points(queries())]

    # Then both points come back, final
    assert [(r.query_id, len(r.points), r.final) for r in responses] == [(3, 2, True)]


class _StreamBackend(_PosedSlam):
    """A per-stream SLAM backend that also holds dense points for every frame it saw."""

    def __init__(self) -> None:
        self.regions = InMemoryRegionPointSource({})

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        self.regions.points_by_frame[frame.frame_id] = (Vec3(0.0, 0.0, 3.0),)
        return super().process_frame(frame)

    def region_points(self, query: RegionQuery, timeout: float = 5.0) -> RegionResult:
        return self.regions.region_points(query, timeout)


async def test_region_points_reach_the_backend_built_for_the_open_survey_stream() -> None:
    # Given a CM5 with no default region source, whose streams that bring camera
    # definitions get a backend of their own
    def per_stream(config: survey_pb2.Cm5StreamConfig) -> _StreamBackend | None:
        return _StreamBackend() if config.cam0_yaml else None

    frame_sent = asyncio.Event()
    done = asyncio.Event()

    async def frames() -> AsyncIterator[survey_pb2.Cm5Request]:
        yield survey_pb2.Cm5Request(
            config=survey_pb2.Cm5StreamConfig(
                calibration=survey_pb2.StereoCalibration(calibration_id="sim"),
                cam0_yaml="cam0",
                cam1_yaml="cam1",
            )
        )
        yield a_frame(7, 0)
        yield a_frame(7, 1)
        frame_sent.set()
        await done.wait()

    async def queries() -> AsyncIterator[survey_pb2.RegionQuery]:
        yield a_region_query(3, 7)

    description = cm5_description(use_stereo=False, slam_factory=per_stream, stream_regions=True)
    async with serving(description) as url:
        async with SurveyConnection.open(url) as connection:
            survey = connection.stream_survey(frames())
            await anext(survey)  # frame 7's scene batch: the stream's backend has the frame
            # When a region on frame 7 is asked for while the survey stream is open
            responses = [r async for r in connection.stream_region_points(queries())]
            done.set()
            _ = [r async for r in survey]

    # Then the stream's own backend answered it
    assert [(r.query_id, r.status, len(r.points)) for r in responses] == [
        (3, survey_pb2.REGION_STATUS_OK, 1)
    ]


async def test_station_analysis_answers_one_response_per_frame_with_its_frame_id() -> None:
    # Given a station whose detector reports one car
    detector = InMemorySamDetector(
        (SamDetection("car", 0.9, (0.0, 0.0, 10.0, 10.0), ((1.0, 1.0),), 7),)
    )

    async def frames() -> AsyncIterator[survey_pb2.StationRequest]:
        yield survey_pb2.StationRequest(
            config=survey_pb2.StationStreamConfig(
                calibration=survey_pb2.StereoCalibration(calibration_id="cal-1"),
                analysis_mode=survey_pb2.ANALYSIS_MODE_EVERY_FRAME,
            )
        )
        for frame_id in (41, 42):
            yield survey_pb2.StationRequest(frame=a_frame(frame_id, 0).frame)

    async with serving(station_description(detector=detector)) as url:
        # When two frames are analyzed over one connection
        async with SurveyConnection.open(url) as connection:
            responses = [r async for r in connection.stream_analysis(frames())]

    # Then each frame got its detections, keyed by its frame_id
    assert [(r.detections.frame_id, r.detections.detections[0].label) for r in responses] == [
        (41, "car"),
        (42, "car"),
    ]


async def test_a_connection_without_the_token_is_refused() -> None:
    # Given a CM5 server guarded by a token
    async with serving(cm5_description(use_stereo=False), TOKEN) as url:
        # When a connection is opened without it
        # Then it is refused before any call
        with pytest.raises(PermissionError):
            async with SurveyConnection.open(url):
                pass


async def test_the_connection_offers_no_compression_because_modal_refuses_it() -> None:
    # Given a listener that records the WebSocket upgrade request and hangs up
    upgrade = asyncio.get_running_loop().create_future()

    async def record(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upgrade.set_result((await reader.readuntil(b"\r\n\r\n")).decode().lower())
        writer.close()

    listener = await asyncio.start_server(record, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        # When a connection is opened to it
        with pytest.raises(OSError):
            async with SurveyConnection.open(f"127.0.0.1:{port}"):
                pass
        request = await upgrade
    finally:
        listener.close()
        await listener.wait_closed()

    # Then the upgrade asks for no permessage-deflate
    assert "sec-websocket-extensions" not in request


@pytest.mark.parametrize(
    ("address", "url"),
    [
        ("10.0.0.5:8080", "ws://10.0.0.5:8080/connect"),
        ("http://10.0.0.5:8080", "ws://10.0.0.5:8080/connect"),
        ("https://ws--surmap-cm5.modal.run", "wss://ws--surmap-cm5.modal.run/connect"),
        ("wss://ws--surmap-cm5.modal.run/connect", "wss://ws--surmap-cm5.modal.run/connect"),
    ],
)
def test_an_address_resolves_to_the_connect_websocket_url(address: str, url: str) -> None:
    assert connect_url(address) == url
