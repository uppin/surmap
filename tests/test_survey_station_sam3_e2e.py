"""Station SAM 3.1 e2e: real socket server, real ONNX Runtime.

The model is the tiny fake SAM3 ONNX graph, executed by the same
`Sam3Detector` + ONNX Runtime session code the station GPU runs
(CUDA provider there, CPU here) — there is no separate test path.
Frames carry a bright box that moves each frame; responses must
segment it per frame, in real time, with the box following. The
server is closed after the run, pass or fail.
"""

import asyncio
import io
import urllib.error
from pathlib import Path

import pytest
from PIL import Image

from surmap.survey.sam3 import sam3_detector
from surmap.survey.station_main import build_description
from surmap.survey.v1 import survey_pb2
from tests.test_survey_server_e2e import _connect_bidi, _get_status, running_server

FAKE_MODEL = Path(__file__).parent / "fixtures" / "sam3_fake" / "fake_sam3.onnx"


def _jpeg(x0: int) -> bytes:
    image = Image.new("RGB", (256, 256), (10, 10, 10))
    for x in range(x0, x0 + 80):
        for y in range(60, 140):
            image.putpixel((x, y), (240, 240, 240))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _requests() -> list[survey_pb2.StationRequest]:
    requests = [
        survey_pb2.StationRequest(
            config=survey_pb2.StationStreamConfig(
                analysis_mode=survey_pb2.ANALYSIS_MODE_EVERY_FRAME
            )
        )
    ]
    for index in range(6):
        requests.append(
            survey_pb2.StationRequest(
                frame=survey_pb2.RawVideoFrame(
                    frame_id=index + 1,
                    t_ns=(index + 1) * 50_000_000,
                    channel=0,
                    width=256,
                    height=256,
                    encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                    data=_jpeg(20 + index * 20),
                )
            )
        )
    return requests


async def test_station_segments_each_frame_through_the_real_runtime() -> None:
    detector = sam3_detector(FAKE_MODEL, device="cpu", label="bright-box")
    assert detector.provider == "CPUExecutionProvider"
    async with running_server(build_description(detector=detector)) as address:
        payloads = await asyncio.to_thread(
            _connect_bidi,
            address,
            "/surmap.survey.v1.StationSamService/StreamAnalysis",
            _requests(),
        )
        assert await asyncio.to_thread(_get_status, address, "/health/is_alive") == 200

    # The server is closed after the run
    with pytest.raises(urllib.error.URLError):
        _get_status(address, "/health/is_alive")

    responses = [survey_pb2.StationResponse.FromString(p) for p in payloads]
    frames = [r.detections for r in responses]
    assert [f.frame_id for f in frames] == [1, 2, 3, 4, 5, 6]
    # Every response names the execution that produced it: this run is
    # the fake model on the CPU provider
    assert {(f.provider, f.device) for f in frames} == {("CPUExecutionProvider", "cpu")}
    x_mins = []
    for frame in frames:
        (detection,) = frame.detections
        assert detection.label == "bright-box"
        assert len(detection.mask_polygon) >= 8
        x_mins.append(detection.box.x_min)
    # The segmented box follows the bright region as it moves right
    assert x_mins == sorted(x_mins)
    assert x_mins[-1] - x_mins[0] >= 80
