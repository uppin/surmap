#!/usr/bin/env python3
"""Verify a deployed station SAM server by feeding it the demo stream.

Feeds the recorded EuRoC demo session's left frames (the same fixture
the CM5 verifier uses) to a running station server over the wire and
verifies the output:

- health: `GET /health/is_alive` answers 200;
- analysis: `StreamAnalysis` answers one response per fed frame,
  frame_ids 1..N in order, with labelled, in-bounds detections that
  carry mask polygons;
- accelerator: every response names the execution that produced it
  (`provider` + `device`), reported as a DEVICE indicator — GPU or
  CPU. `--expect-device gpu|cpu` fails the run when the station ran
  somewhere else (e.g. a silent CPU fallback).

    uv run python scripts/fetch_rtabmap_fixture.py
    uv run python scripts/verify_station.py 10.88.77.10:8081 --expect-device gpu

Exits 0 only when every check passes. No target is stored in the
repo: the address is a CLI argument, as with the deploy scripts.
"""

from __future__ import annotations

import argparse
import http.client
import json
import struct
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from surmap.survey.v1 import survey_pb2  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "euroc_v101_rtabmap"
FRAME_WIDTH = 376
FRAME_HEIGHT = 240


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class Rate:
    """Frames processed per second over one measured run."""

    name: str
    frames: int
    elapsed_s: float

    @property
    def fps(self) -> float:
        return self.frames / self.elapsed_s if self.elapsed_s > 0 else 0.0


@dataclass(frozen=True)
class VerifyReport:
    checks: list[CheckResult]
    rates: list[Rate]


def load_timestamps(fixture_dir: Path, frame_count: int) -> list[int]:
    """The first `frame_count` frame timestamps of the recorded session."""
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    return [int(value) for value in manifest["frame_timestamps_ns"][:frame_count]]


def check_analysis(
    responses: list[survey_pb2.StationResponse],
    *,
    width: int,
    height: int,
    min_frames_with_detections: int,
) -> list[str]:
    failures: list[str] = []
    frames = [response.detections for response in responses]
    frame_ids = [frame.frame_id for frame in frames]
    if frame_ids != list(range(1, len(responses) + 1)):
        failures.append(f"analysis frame_id sequence is {frame_ids}, expected 1..{len(responses)}")
    for frame in frames:
        if not frame.provider or not frame.device:
            failures.append(
                f"frame {frame.frame_id}: response carries no provider/device, "
                "so GPU vs CPU execution is unreported"
            )
            break
    with_detections = [frame for frame in frames if frame.detections]
    if len(with_detections) < min_frames_with_detections:
        failures.append(
            f"only {len(with_detections)} frames carry detections, "
            f"expected at least {min_frames_with_detections}"
        )
    for frame in with_detections:
        for detection in frame.detections:
            if not detection.label:
                failures.append(f"frame {frame.frame_id}: detection has an empty label")
            if not 0.0 < detection.score <= 1.0:
                failures.append(f"frame {frame.frame_id}: score {detection.score} outside (0, 1]")
            box = detection.box
            if not (0 <= box.x_min < box.x_max <= width and 0 <= box.y_min < box.y_max <= height):
                failures.append(
                    f"frame {frame.frame_id}: box ({box.x_min}, {box.y_min}, "
                    f"{box.x_max}, {box.y_max}) escapes the {width}x{height} image"
                )
            if not detection.mask_polygon:
                failures.append(f"frame {frame.frame_id}: detection has no mask polygon")
    return failures


def device_kind(responses: list[survey_pb2.StationResponse]) -> str:
    """ "gpu", "cpu", or "unknown", from what the responses report."""
    executions = {
        (response.detections.provider, response.detections.device) for response in responses
    }
    executions.discard(("", ""))
    if not executions:
        return "unknown"
    for provider, device in executions:
        if device.startswith("cuda") or "CUDA" in provider:
            return "gpu"
    return "cpu"


def device_indicator(responses: list[survey_pb2.StationResponse]) -> str:
    """The one-line GPU/CPU indicator, with the evidence it was read from."""
    kind = device_kind(responses)
    if kind == "unknown":
        return "UNKNOWN (responses carry no provider/device)"
    provider, device = sorted(
        {(r.detections.provider, r.detections.device) for r in responses} - {("", "")}
    )[0]
    return f"{kind.upper()} (provider={provider}, device={device})"


def _frame_message(message: survey_pb2.StationRequest) -> bytes:
    payload = message.SerializeToString()
    return struct.pack(">BI", 0, len(payload)) + payload


def _post_stream(address: str, requests: list[survey_pb2.StationRequest]) -> list[bytes]:
    body = b"".join(_frame_message(request) for request in requests)
    connection = http.client.HTTPConnection(address, timeout=300)
    try:
        connection.request(
            "POST",
            "/surmap.survey.v1.StationSamService/StreamAnalysis",
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
        if flag == 2:
            break
        payloads.append(payload)
        offset += 5 + length
    return payloads


def verify(
    address: str,
    fixture_dir: Path,
    frame_count: int = 6,
    *,
    min_frames_with_detections: int = 1,
    expect_device: str = "any",
) -> VerifyReport:
    """Feed the demo stream to the station at `address`.

    One check per concern, plus the analysis frame rate. The
    accelerator check reads the GPU/CPU indication from the responses
    themselves; `expect_device` ("gpu"/"cpu") makes a mismatch fail.
    """
    results: list[CheckResult] = []
    rates: list[Rate] = []
    try:
        with urllib.request.urlopen(f"http://{address}/health/is_alive", timeout=10) as response:
            status = int(response.status)  # type: ignore[attr-defined]
        results.append(CheckResult("health", status == 200, f"GET /health/is_alive -> {status}"))
    except Exception as exc:  # a dead server fails every later check too
        detail = f"GET /health/is_alive failed: {exc}"
        return VerifyReport(
            [
                CheckResult("health", False, detail),
                CheckResult("analysis", False, "not run: server unreachable"),
                CheckResult("accelerator", False, "not run: server unreachable"),
            ],
            rates,
        )

    timestamps = load_timestamps(fixture_dir, frame_count)
    requests = [
        survey_pb2.StationRequest(
            config=survey_pb2.StationStreamConfig(
                calibration=survey_pb2.StereoCalibration(calibration_id="euroc-verify"),
                analysis_mode=survey_pb2.ANALYSIS_MODE_EVERY_FRAME,
            )
        )
    ]
    for index, t_ns in enumerate(timestamps):
        data = (fixture_dir / "mav0" / "cam0" / "data" / f"{t_ns}.jpg").read_bytes()
        requests.append(
            survey_pb2.StationRequest(
                frame=survey_pb2.RawVideoFrame(
                    frame_id=index + 1,
                    t_ns=t_ns,
                    channel=0,
                    width=FRAME_WIDTH,
                    height=FRAME_HEIGHT,
                    encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                    data=data,
                )
            )
        )
    started = time.perf_counter()
    payloads = _post_stream(address, requests)
    rates.append(Rate("station-analysis", len(timestamps), time.perf_counter() - started))
    responses = [survey_pb2.StationResponse.FromString(payload) for payload in payloads]

    failures = check_analysis(
        responses,
        width=FRAME_WIDTH,
        height=FRAME_HEIGHT,
        min_frames_with_detections=min_frames_with_detections,
    )
    with_detections = sum(1 for r in responses if r.detections.detections)
    results.append(
        CheckResult(
            "analysis",
            not failures,
            failures[0]
            if failures
            else f"{with_detections}/{len(responses)} frames carry SAM detections",
        )
    )

    kind = device_kind(responses)
    indicator = device_indicator(responses)
    expected_ok = expect_device in ("any", kind)
    results.append(
        CheckResult(
            "accelerator",
            kind != "unknown" and expected_ok,
            indicator if expected_ok else f"{indicator} (expected {expect_device.upper()})",
        )
    )
    return VerifyReport(results, rates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", help="station server address, e.g. 10.88.77.10:8081")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--min-detection-frames", type=int, default=1)
    parser.add_argument("--expect-device", choices=("any", "gpu", "cpu"), default="any")
    args = parser.parse_args(argv)
    report = verify(
        args.address,
        args.fixture,
        args.frames,
        min_frames_with_detections=args.min_detection_frames,
        expect_device=args.expect_device,
    )
    for result in report.checks:
        print(f"{'PASS' if result.ok else 'FAIL'} {result.name}: {result.detail}")
    for rate in report.rates:
        print(
            f"RATE {rate.name}: {rate.fps:.1f} fps ({rate.frames} frames in {rate.elapsed_s:.2f}s)"
        )
    for result in report.checks:
        if result.name == "accelerator":
            print(f"DEVICE station: {result.detail}")
    return 0 if all(result.ok for result in report.checks) else 1


if __name__ == "__main__":
    sys.exit(main())
