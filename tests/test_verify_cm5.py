"""Fluent tests for `scripts/verify_cm5.py`.

The script feeds the recorded EuRoC demo stream (the same session
fixture as the Coral e2e) to a deployed CM5 server and verifies the
output: health, the detections stream, and the survey point stream.
These tests pin the check logic on synthetic wire messages, plus one
session-replay run against a real local server.
"""

import asyncio
import importlib.util
import json
import os
import pathlib
import sys

import pytest

from surmap.survey.v1 import survey_pb2

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "verify_cm5.py"
FIXTURES = ROOT / "tests" / "fixtures"
EUROC = FIXTURES / "euroc_v101_rtabmap"
MODEL_DIR = FIXTURES / "coral_model"
REQUIRED = os.environ.get("SURMAP_REQUIRE_CORAL_E2E") == "1"


def _load_verify() -> object:
    spec = importlib.util.spec_from_file_location("verify_cm5", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_cm5"] = module
    spec.loader.exec_module(module)
    return module


verify_cm5 = _load_verify()


def a_detection_message(
    frame_id: int, *, label: str = "chair", score: float = 0.8, track_id: int = 1
) -> survey_pb2.FrameDetections:
    return survey_pb2.FrameDetections(
        frame_id=frame_id,
        t_ns=frame_id * 1_000_000,
        detections=[
            survey_pb2.ObjectDetection(
                label=label,
                score=score,
                box=survey_pb2.Box(x_min=10.0, y_min=20.0, x_max=110.0, y_max=120.0),
                track_id=track_id,
            )
        ],
    )


def an_empty_message(frame_id: int) -> survey_pb2.FrameDetections:
    return survey_pb2.FrameDetections(frame_id=frame_id, t_ns=frame_id * 1_000_000)


def a_points_response(designation: int, count: int) -> survey_pb2.Cm5Response:
    return survey_pb2.Cm5Response(
        points=survey_pb2.PointBatch(
            designation=designation,
            frame_id=1,
            t_ns=1_000_000,
            points=[survey_pb2.Point3(x=1.0, y=2.0, z=3.0)] * count,
        )
    )


def test_tracked_detections_in_frame_order_pass_the_detections_check() -> None:
    # Given one tracked detection on each of five frames, in order
    messages = [a_detection_message(frame_id) for frame_id in range(1, 6)]

    # When the detections output is checked
    failures = verify_cm5.check_detections(  # type: ignore[attr-defined]
        messages, width=376, height=240, min_frames_with_detections=3, min_track_length=3
    )

    # Then there is nothing to report
    assert failures == []


def test_detections_arriving_out_of_order_fail_the_detections_check() -> None:
    # Given detections whose frame ids do not run 1..N in order
    messages = [a_detection_message(1), a_detection_message(3), a_detection_message(2)]

    # When the detections output is checked
    failures = verify_cm5.check_detections(  # type: ignore[attr-defined]
        messages, width=376, height=240, min_frames_with_detections=1, min_track_length=1
    )

    # Then the ordering failure is named
    assert any("frame_id" in failure for failure in failures)


def test_a_stream_with_no_detections_at_all_fails_the_detections_check() -> None:
    # Given a server that answered every frame with no detections
    messages = [an_empty_message(frame_id) for frame_id in range(1, 6)]

    # When the detections output is checked
    failures = verify_cm5.check_detections(  # type: ignore[attr-defined]
        messages, width=376, height=240, min_frames_with_detections=3, min_track_length=3
    )

    # Then the missing detector output is named
    assert any("detections" in failure for failure in failures)


def test_a_box_escaping_the_image_fails_the_detections_check() -> None:
    # Given a detection whose box runs past the right edge of the image
    message = a_detection_message(1)
    message.detections[0].box.x_max = 999.0

    # When the detections output is checked
    failures = verify_cm5.check_detections(  # type: ignore[attr-defined]
        [message], width=376, height=240, min_frames_with_detections=1, min_track_length=1
    )

    # Then the box failure is named
    assert any("box" in failure for failure in failures)


def test_scene_and_object_points_pass_the_survey_check() -> None:
    # Given a static-scene batch and one tracked object's batch
    responses = [a_points_response(1, 10), a_points_response(101, 60)]

    # When the survey output is checked
    failures = verify_cm5.check_survey(responses, min_object_points=50)  # type: ignore[attr-defined]

    # Then there is nothing to report
    assert failures == []


def test_survey_output_without_object_points_fails_the_survey_check() -> None:
    # Given scene points only — the detector never lifted an object
    responses = [a_points_response(1, 10)]

    # When the survey output is checked
    failures = verify_cm5.check_survey(responses, min_object_points=50)  # type: ignore[attr-defined]

    # Then the missing object layer is named
    assert any("object" in failure for failure in failures)


def _require_prepared() -> None:
    if not (MODEL_DIR / "manifest.json").is_file() or not (EUROC / "manifest.json").is_file():
        message = "run `uv run python scripts/fetch_coral_model.py` and fetch_rtabmap_fixture.py"
        if REQUIRED:
            pytest.fail(message)
        pytest.skip(message)


async def test_verify_passes_against_a_server_running_the_real_detector() -> None:
    _require_prepared()
    from surmap.detection.detector import CoralDetector
    from surmap.detection.source import CoralDetectionSource, CoralObjectPointSource
    from surmap.survey.cm5_main import build_description
    from surmap.survey.stereo import StereoReconstructor
    from tests.test_survey_server_e2e import running_server

    # Given a real CM5 server whose detector is the real Coral network on CPU
    detector = CoralDetector(
        MODEL_DIR / "efficientdet_lite0_320_ptq.tflite", MODEL_DIR / "coco_labels.txt"
    )
    source = CoralDetectionSource(detector)
    objects = CoralObjectPointSource(source, StereoReconstructor())
    description = build_description(objects=objects, detections=source)

    # When the demo stream is fed to it by the verification script
    async with running_server(description) as address:
        report = await asyncio.to_thread(verify_cm5.verify, address, EUROC)  # type: ignore[attr-defined]

    # Then every check passes, and a frame rate is measured per stream
    assert {result.name for result in report.checks} == {"health", "detections", "survey"}
    assert all(result.ok for result in report.checks), [r.detail for r in report.checks]
    assert {rate.name for rate in report.rates} == {"coral-detections", "survey"}
    assert all(rate.fps > 0 for rate in report.rates)


async def test_verify_fails_against_a_server_without_a_detector() -> None:
    _require_prepared()
    from surmap.survey.cm5_main import build_description
    from tests.test_survey_server_e2e import running_server

    # Given a CM5 server with the default no-detector configuration
    async with running_server(build_description()) as address:
        # When the demo stream is fed to it by the verification script
        report = await asyncio.to_thread(verify_cm5.verify, address, EUROC)  # type: ignore[attr-defined]

    # Then health passes but the detector-dependent checks fail
    by_name = {result.name: result for result in report.checks}
    assert by_name["health"].ok
    assert not by_name["detections"].ok
    assert not by_name["survey"].ok


def test_backend_frame_rate_counts_only_the_frames_that_came_back_posed() -> None:
    _require_prepared()
    from surmap.slam.fake import InMemorySlamBackend

    # Given a backend that poses every frame it is fed
    backend = InMemorySlamBackend()

    # When its frame rate is measured on the demo stream
    rate = verify_cm5.measure_backend_fps(backend, EUROC, 10)  # type: ignore[attr-defined]

    # Then every fed frame is counted, at a positive rate
    assert rate.name == "rtabmap"
    assert rate.frames == 10
    assert rate.fps > 0
    assert rate.dropped == 0


def test_rtabmap_only_mode_measures_the_backend_without_a_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _require_prepared()
    # Given a stand-in for the local RTAB-Map sidecar measurement
    measured: list[int] = []

    def fake_measure(
        fixture_dir: pathlib.Path, frame_count: int, native_binary: object = None
    ) -> object:
        measured.append(frame_count)
        return verify_cm5.Rate("rtabmap", 18, 0.6)  # type: ignore[attr-defined]

    monkeypatch.setattr(verify_cm5, "measure_rtabmap_fps", fake_measure)

    # When the script runs in RTAB-Map-only mode — no server address,
    # so no detector, no object tracking, no survey stream
    exit_code = verify_cm5.main(["--rtabmap-only", "--frames", "20"])  # type: ignore[attr-defined]

    # Then it reports the backend's posed-frame rate and passes
    assert exit_code == 0
    assert measured == [20]
    assert "RATE rtabmap: 30.0 fps (18 frames" in capsys.readouterr().out


def test_the_script_reports_its_fixture_manifest_frame_count() -> None:
    _require_prepared()
    # Given the recorded EuRoC demo session on disk
    timestamps = json.loads((EUROC / "manifest.json").read_text(encoding="utf-8"))[
        "frame_timestamps_ns"
    ]

    # When the script loads the stream it will feed
    frames = verify_cm5.load_timestamps(EUROC, 40)  # type: ignore[attr-defined]

    # Then it takes the first frames of the session, in order
    assert frames == [int(value) for value in timestamps[:40]]
