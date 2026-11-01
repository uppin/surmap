"""Fluent tests for `scripts/verify_station.py`.

The script feeds the recorded EuRoC demo stream (the same session
fixture as the CM5 verifier) to a deployed station SAM server and
verifies the output: health, one analysis response per frame, and —
the point of the exercise — an indicator, taken from the responses
themselves, of whether SAM ran on the GPU or the CPU. These tests pin
the check logic on synthetic wire messages, plus one session-replay
run against a real local server (the fake SAM3 model on CPU).
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from surmap.survey.v1 import survey_pb2

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "verify_station.py"
FIXTURES = ROOT / "tests" / "fixtures"
EUROC = FIXTURES / "euroc_v101_rtabmap"
FAKE_MODEL = FIXTURES / "sam3_fake" / "fake_sam3.onnx"


def _load_verify() -> object:
    spec = importlib.util.spec_from_file_location("verify_station", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_station"] = module
    spec.loader.exec_module(module)
    return module


verify_station = _load_verify()


def a_response(
    frame_id: int,
    *,
    provider: str = "SAM 3.1 (PyTorch)",
    device: str = "cuda:0",
    label: str = "wall",
) -> survey_pb2.StationResponse:
    return survey_pb2.StationResponse(
        detections=survey_pb2.SamFrameDetections(
            frame_id=frame_id,
            provider=provider,
            device=device,
            detections=[
                survey_pb2.SamDetection(
                    label=label,
                    score=0.85,
                    box=survey_pb2.Box(x_min=10.0, y_min=20.0, x_max=110.0, y_max=120.0),
                    mask_polygon=[
                        survey_pb2.Point2(x=10.0, y=20.0),
                        survey_pb2.Point2(x=110.0, y=20.0),
                        survey_pb2.Point2(x=110.0, y=120.0),
                    ],
                )
            ],
        )
    )


def an_empty_response(frame_id: int, **kwargs: object) -> survey_pb2.StationResponse:
    response = a_response(frame_id, **kwargs)  # type: ignore[arg-type]
    del response.detections.detections[:]
    return response


def test_ordered_segmented_frames_pass_the_analysis_check() -> None:
    # Given one segmented frame per request, in order, GPU-executed
    responses = [a_response(frame_id) for frame_id in range(1, 7)]

    # When the station output is checked
    failures = verify_station.check_analysis(  # type: ignore[attr-defined]
        responses, width=376, height=240, min_frames_with_detections=3
    )

    # Then there is nothing to report
    assert failures == []


def test_responses_without_execution_fields_fail_the_analysis_check() -> None:
    # Given responses from a server that does not say where SAM ran
    responses = [a_response(1, provider="", device=""), a_response(2, provider="", device="")]

    # When the station output is checked
    failures = verify_station.check_analysis(  # type: ignore[attr-defined]
        responses, width=376, height=240, min_frames_with_detections=1
    )

    # Then the missing GPU/CPU indication is named
    assert any("provider" in failure or "device" in failure for failure in failures)


def test_frames_arriving_out_of_order_fail_the_analysis_check() -> None:
    # Given responses whose frame ids do not run 1..N in order
    responses = [a_response(1), a_response(3), a_response(2)]

    # When the station output is checked
    failures = verify_station.check_analysis(  # type: ignore[attr-defined]
        responses, width=376, height=240, min_frames_with_detections=1
    )

    # Then the ordering failure is named
    assert any("frame_id" in failure for failure in failures)


def test_a_gpu_execution_reads_as_gpu_in_the_indicator() -> None:
    # Given responses the station produced on its first CUDA device
    responses = [a_response(1), a_response(2)]

    # When the execution indicator is read from the responses
    indicator = verify_station.device_indicator(responses)  # type: ignore[attr-defined]

    # Then it says GPU, with the evidence it read it from
    assert indicator.startswith("GPU")
    assert "cuda:0" in indicator


def test_a_cpu_execution_reads_as_cpu_in_the_indicator() -> None:
    # Given responses produced by the ONNX CPU provider
    responses = [a_response(1, provider="CPUExecutionProvider", device="cpu")]

    # When the execution indicator is read from the responses
    indicator = verify_station.device_indicator(responses)  # type: ignore[attr-defined]

    # Then it says CPU, not GPU
    assert indicator.startswith("CPU")
    assert "CPUExecutionProvider" in indicator


def _require_prepared() -> None:
    if not (EUROC / "manifest.json").is_file() or not FAKE_MODEL.is_file():
        pytest.skip("run `uv run python scripts/fetch_rtabmap_fixture.py` first")


async def test_verify_passes_and_reports_cpu_against_the_fake_model_server() -> None:
    _require_prepared()
    from surmap.survey.sam3 import sam3_detector
    from surmap.survey.station_main import build_description
    from tests.test_survey_server_e2e import running_server

    # Given a real station server running the fake SAM3 model on CPU
    detector = sam3_detector(FAKE_MODEL, device="cpu", label="wall")
    async with running_server(build_description(detector=detector)) as address:
        # When the demo stream is fed to it by the verification script
        report = await asyncio.to_thread(verify_station.verify, address, EUROC)  # type: ignore[attr-defined]

    # Then every check passes, and the indicator says CPU
    assert all(result.ok for result in report.checks), [r.detail for r in report.checks]
    assert {result.name for result in report.checks} == {"health", "analysis", "accelerator"}
    accelerator = next(r for r in report.checks if r.name == "accelerator")
    assert accelerator.detail.startswith("CPU")
    assert report.rates and report.rates[0].fps > 0


async def test_verify_expecting_gpu_fails_against_a_cpu_server() -> None:
    _require_prepared()
    from surmap.survey.sam3 import sam3_detector
    from surmap.survey.station_main import build_description
    from tests.test_survey_server_e2e import running_server

    # Given the same CPU server, verified with a GPU expectation
    detector = sam3_detector(FAKE_MODEL, device="cpu", label="wall")
    async with running_server(build_description(detector=detector)) as address:
        report = await asyncio.to_thread(
            verify_station.verify,  # type: ignore[attr-defined]
            address,
            EUROC,
            expect_device="gpu",
        )

    # Then the accelerator check fails, naming what actually ran
    accelerator = next(r for r in report.checks if r.name == "accelerator")
    assert not accelerator.ok
    assert accelerator.detail.startswith("CPU")
