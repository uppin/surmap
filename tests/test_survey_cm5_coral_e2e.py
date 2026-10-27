"""Real Coral-detector e2e: EuRoC frames through the real CM5 server.

The detector is the real EfficientDet-Lite0 INT8 network running via
LiteRT on CPU (its `_edgetpu` twin is for Coral boards; there is no
board in CI — see docs/coral-edge-tpu-model-spike.md). Two streams
are exercised against the same frames:

- `StreamDetections` — the separate detections stream: messages keyed
  by frame_id with tracked boxes, on the detector's own cadence, not
  attached to survey output frames;
- `StreamSurvey` — the same detector+tracker lifting stereo points
  into object batches at designations >= 100.

Prepared by tooling, nothing installed on the host:

    uv run python scripts/fetch_coral_model.py
    uv run python scripts/fetch_rtabmap_fixture.py   # EuRoC subset

Without preparation this skips (fails when
`SURMAP_REQUIRE_CORAL_E2E=1`, as CI sets). Server closed afterwards.
"""

import asyncio
import json
import os
import pathlib
import urllib.error

import pytest

from surmap.demo.datasets import DATASETS, PreparedDataset, load_calibration
from surmap.detection.detector import CoralDetector
from surmap.detection.source import CoralDetectionSource, CoralObjectPointSource
from surmap.survey.cm5_main import build_description
from surmap.survey.stereo import StereoReconstructor, StereoRig
from surmap.survey.v1 import survey_pb2
from tests.test_survey_server_e2e import _connect_bidi, _get_status, running_server

ROOT = pathlib.Path(__file__).parent / "fixtures"
MODEL_DIR = ROOT / "coral_model"
EUROC = ROOT / "euroc_v101_rtabmap"
REQUIRED = os.environ.get("SURMAP_REQUIRE_CORAL_E2E") == "1"
FRAME_COUNT = 40


def _require_prepared() -> list[int]:
    if not (MODEL_DIR / "manifest.json").is_file() or not (EUROC / "manifest.json").is_file():
        message = (
            "Coral e2e not prepared: run `uv run python scripts/fetch_coral_model.py` "
            "and `uv run python scripts/fetch_rtabmap_fixture.py` first"
        )
        if REQUIRED:
            pytest.fail(message)
        pytest.skip(message)
    manifest = json.loads((EUROC / "manifest.json").read_text(encoding="utf-8"))
    timestamps: list[int] = [int(value) for value in manifest["frame_timestamps_ns"]]
    return timestamps[:FRAME_COUNT]


def _frame(frame_id: int, t_ns: int, channel: int) -> survey_pb2.Cm5Request:
    data = (EUROC / "mav0" / f"cam{channel}" / "data" / f"{t_ns}.jpg").read_bytes()
    return survey_pb2.Cm5Request(
        frame=survey_pb2.RawVideoFrame(
            frame_id=frame_id,
            t_ns=t_ns,
            channel=channel,
            width=376,
            height=240,
            encoding=survey_pb2.FRAME_ENCODING_MJPEG,
            data=data,
        )
    )


def _config() -> survey_pb2.Cm5Request:
    return survey_pb2.Cm5Request(
        config=survey_pb2.Cm5StreamConfig(
            calibration=survey_pb2.StereoCalibration(calibration_id="euroc-coral"),
            video_channels=[],
        )
    )


async def test_real_detections_stream_and_object_points() -> None:
    timestamps = _require_prepared()
    detector = CoralDetector(
        MODEL_DIR / "efficientdet_lite0_320_ptq.tflite", MODEL_DIR / "coco_labels.txt"
    )
    source = CoralDetectionSource(detector)
    calibration = load_calibration(PreparedDataset(DATASETS["euroc-v1-01-easy"], EUROC, ())).scaled(
        376, 240
    )
    rig = StereoRig(
        calibration.fx, calibration.fy, calibration.cx, calibration.cy, calibration.baseline_m
    )
    objects = CoralObjectPointSource(source, StereoReconstructor(), rig)
    description = build_description(objects=objects, detections=source, use_stereo=False)

    async with running_server(description) as address:
        # Given the separate detections stream over the real frames
        detection_requests = [_config()] + [
            _frame(index + 1, t_ns, 0) for index, t_ns in enumerate(timestamps)
        ]
        payloads = await asyncio.to_thread(
            _connect_bidi,
            address,
            "/surmap.survey.v1.Cm5SurveyService/StreamDetections",
            detection_requests,
        )
        detection_messages = [
            survey_pb2.DetectionResponse.FromString(payload).detections for payload in payloads
        ]

        # And the survey stream over the same pairs
        survey_requests = [_config()]
        for index, t_ns in enumerate(timestamps):
            survey_requests += [_frame(index + 1, t_ns, 0), _frame(index + 1, t_ns, 1)]
        payloads = await asyncio.to_thread(
            _connect_bidi,
            address,
            "/surmap.survey.v1.Cm5SurveyService/StreamSurvey",
            survey_requests,
        )
        responses = [survey_pb2.Cm5Response.FromString(payload) for payload in payloads]
        assert await asyncio.to_thread(_get_status, address, "/health/is_alive") == 200

    # Then the server is closed after the run
    with pytest.raises(urllib.error.URLError):
        _get_status(address, "/health/is_alive")

    # The detections stream stood alone: keyed by frame_id, in order,
    # with real tracked detections on many of the analyzed frames
    assert [m.frame_id for m in detection_messages] == list(range(1, len(timestamps) + 1))
    with_detections = [m for m in detection_messages if m.detections]
    assert len(with_detections) >= 10
    for message in with_detections:
        for detection in message.detections:
            assert detection.label
            assert 0.3 <= detection.score <= 1.0
            assert detection.HasField("track_id")
            assert 0 <= detection.box.x_min < detection.box.x_max <= 376
            assert 0 <= detection.box.y_min < detection.box.y_max <= 240
    appearances: dict[int, int] = {}
    for message in with_detections:
        for detection in message.detections:
            appearances[detection.track_id] = appearances.get(detection.track_id, 0) + 1
    assert max(appearances.values()) >= 3, f"no persistent track in {appearances}"

    # And the survey stream carried real object points under tracked
    # object designations (>= 100), from the same detector+tracker
    batches = [r.points for r in responses if r.WhichOneof("kind") == "points"]
    object_batches = [batch for batch in batches if batch.designation >= 100]
    assert object_batches, "no object point batches from the real detector"
    assert all(batch.designation >= 100 for batch in object_batches)
    assert sum(len(batch.points) for batch in object_batches) > 50
