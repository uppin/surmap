"""Real-server e2es: each server starts on a real socket, is exercised
over the wire, and is closed after the run — pass or fail.
"""

import asyncio
import http.client
import json
import struct
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from google.protobuf.message import Message

from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.slam.base import FrameResult
from surmap.survey.cm5_main import build_description as build_cm5_description
from surmap.survey.sam import InMemorySamDetector, SamDetection
from surmap.survey.station_main import build_description as build_station_description
from surmap.survey.v1 import survey_pb2
from surmap.types import Pose, StereoFramePair, Vec3


@asynccontextmanager
async def running_server(description: object) -> AsyncIterator[str]:
    """Start a real server on an ephemeral port; always stop it after."""
    host = HypercornHost(description, None, host="127.0.0.1", port=0)  # type: ignore[arg-type]
    ports = await host.start()
    try:
        yield f"127.0.0.1:{ports.public}"
    finally:
        await host.stop()


def _frame_message(message: Message) -> bytes:
    payload = message.SerializeToString()
    return struct.pack(">BI", 0, len(payload)) + payload


def _connect_bidi(address: str, path: str, requests: list[Message]) -> list[bytes]:
    """POST framed Connect stream messages; return framed response payloads."""
    body = b"".join(_frame_message(request) for request in requests)
    connection = http.client.HTTPConnection(address, timeout=10)
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={"content-type": "application/connect+proto"},
        )
        raw = connection.getresponse().read()
    finally:
        connection.close()
    payloads: list[bytes] = []
    offset = 0
    while offset < len(raw):
        flag, length = struct.unpack(">BI", raw[offset : offset + 5])
        payload = raw[offset + 5 : offset + 5 + length]
        if flag == 2:  # end-of-stream trailer frame
            assert json.loads(payload or b"{}") == {}
            break
        payloads.append(payload)
        offset += 5 + length
    return payloads


def _get_status(address: str, path: str) -> int:
    with urllib.request.urlopen(f"http://{address}{path}", timeout=5) as response:
        return int(response.status)


class _FakeSlam:
    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        return FrameResult(
            frame.frame_id, frame.t_ns, Pose(Vec3(0.0, 0.0, 0.0)), (Vec3(1.0, 2.0, 3.0),)
        )

    def trajectory(self) -> list[Pose]:
        return []

    def close(self) -> None:
        pass


def _cm5_requests() -> list[Message]:
    config = survey_pb2.Cm5Request(
        config=survey_pb2.Cm5StreamConfig(
            calibration=survey_pb2.StereoCalibration(calibration_id="cal-1"),
            video_channels=[0],
        )
    )
    frames = [
        survey_pb2.Cm5Request(
            frame=survey_pb2.RawVideoFrame(
                frame_id=1,
                t_ns=1_000_000,
                channel=channel,
                width=640,
                height=480,
                encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                data=b"f",
            )
        )
        for channel in (0, 1)
    ]
    return [config, *frames]


async def test_the_cm5_server_answers_over_a_real_socket_and_closes_afterwards() -> None:
    # Given the real CM5 server on an ephemeral port
    async with running_server(build_cm5_description(slam=_FakeSlam())) as address:
        # When a client streams a pair over the wire
        payloads = await asyncio.to_thread(
            _connect_bidi,
            address,
            "/surmap.survey.v1.Cm5SurveyService/StreamSurvey",
            _cm5_requests(),
        )
        responses = []
        for payload in payloads:
            response = survey_pb2.Cm5Response()
            response.ParseFromString(payload)
            responses.append(response)

        # Then the video echo and the scene batch both arrive, and health is alive
        kinds = [r.WhichOneof("kind") for r in responses]
        assert kinds == ["video", "points"]
        assert responses[1].points.designation == 1
        assert await asyncio.to_thread(_get_status, address, "/health/is_alive") == 200

    # And after the run the server is closed: the port refuses connections
    with pytest.raises(urllib.error.URLError):
        _get_status(address, "/health/is_alive")


async def test_the_station_server_answers_over_a_real_socket_and_closes_afterwards() -> None:
    detector = InMemorySamDetector(
        (SamDetection("car", 0.9, (0.0, 0.0, 10.0, 10.0), ((1.0, 1.0),), 7),)
    )
    async with running_server(build_station_description(detector=detector)) as address:
        config = survey_pb2.StationRequest(
            config=survey_pb2.StationStreamConfig(
                calibration=survey_pb2.StereoCalibration(calibration_id="cal-1"),
                analysis_mode=survey_pb2.ANALYSIS_MODE_EVERY_FRAME,
            )
        )
        frame = survey_pb2.StationRequest(
            frame=survey_pb2.RawVideoFrame(
                frame_id=42,
                t_ns=1_000_000,
                channel=0,
                width=640,
                height=480,
                encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                data=b"f",
            )
        )
        payloads = await asyncio.to_thread(
            _connect_bidi,
            address,
            "/surmap.survey.v1.StationSamService/StreamAnalysis",
            [config, frame],
        )
        (response,) = [survey_pb2.StationResponse.FromString(p) for p in payloads]
        assert response.detections.frame_id == 42
        assert response.detections.detections[0].label == "car"

    with pytest.raises(urllib.error.URLError):
        _get_status(address, "/health/is_alive")


async def test_a_failing_e2e_still_closes_its_server() -> None:
    # Given a run that fails mid-test
    address = ""
    with pytest.raises(AssertionError):
        async with running_server(build_station_description()) as running:
            address = running
            raise AssertionError("simulated failure")

    # Then the server was still closed by the fixture's finally
    with pytest.raises(urllib.error.URLError):
        _get_status(address, "/health/is_alive")
