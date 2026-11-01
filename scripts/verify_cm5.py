#!/usr/bin/env python3
"""Verify a deployed CM5 survey server by feeding it the demo stream.

Feeds the recorded EuRoC demo session (the fixture prepared by
`scripts/fetch_rtabmap_fixture.py`, the same frames the Coral e2e
uses) to a running CM5 server over the wire and verifies the output:

- health: `GET /health/is_alive` answers 200;
- detections: `StreamDetections` answers one message per fed frame,
  frame_ids 1..N in order, with labelled, tracked, in-bounds boxes on
  enough frames and at least one persistent track;
- survey: `StreamSurvey` answers static-scene points (designation 1)
  and tracked-object points (designation >= 100).

    uv run python scripts/fetch_coral_model.py
    uv run python scripts/fetch_rtabmap_fixture.py
    uv run python scripts/verify_cm5.py 10.88.77.237:8080

To measure the RTAB-Map streaming sidecar alone — no server, no
Coral detector, no object tracking, recorded pairs straight into
the backend (needs Docker):

    uv run python scripts/verify_cm5.py --rtabmap-only [--frames N]

Exits 0 only when every check passes. No target is stored in the
repo: the address is a CLI argument, as with the deploy scripts.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import struct
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from surmap.demo.datasets import DATASETS, PreparedDataset, load_calibration  # noqa: E402
from surmap.slam.base import SlamBackend  # noqa: E402
from surmap.survey.v1 import survey_pb2  # noqa: E402
from surmap.types import StereoFramePair  # noqa: E402

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
    dropped: int = 0

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


def check_detections(
    messages: list[survey_pb2.FrameDetections],
    *,
    width: int,
    height: int,
    min_frames_with_detections: int,
    min_track_length: int,
) -> list[str]:
    failures: list[str] = []
    frame_ids = [message.frame_id for message in messages]
    if frame_ids != list(range(1, len(messages) + 1)):
        failures.append(f"detections frame_id sequence is {frame_ids}, expected 1..{len(messages)}")
    with_detections = [message for message in messages if message.detections]
    if len(with_detections) < min_frames_with_detections:
        failures.append(
            f"only {len(with_detections)} frames carry detections, "
            f"expected at least {min_frames_with_detections}"
        )
    appearances: dict[int, int] = {}
    for message in with_detections:
        for detection in message.detections:
            if not detection.label:
                failures.append(f"frame {message.frame_id}: detection has an empty label")
            if not 0.3 <= detection.score <= 1.0:
                failures.append(
                    f"frame {message.frame_id}: score {detection.score} outside [0.3, 1.0]"
                )
            box = detection.box
            if not (0 <= box.x_min < box.x_max <= width and 0 <= box.y_min < box.y_max <= height):
                failures.append(
                    f"frame {message.frame_id}: box ({box.x_min}, {box.y_min}, "
                    f"{box.x_max}, {box.y_max}) escapes the {width}x{height} image"
                )
            if not detection.HasField("track_id"):
                failures.append(f"frame {message.frame_id}: detection has no track_id")
            else:
                appearances[detection.track_id] = appearances.get(detection.track_id, 0) + 1
    if appearances and max(appearances.values()) < min_track_length:
        failures.append(
            f"longest track runs {max(appearances.values())} frames, "
            f"expected at least {min_track_length}"
        )
    return failures


def check_survey(responses: list[survey_pb2.Cm5Response], *, min_object_points: int) -> list[str]:
    failures: list[str] = []
    batches = [r.points for r in responses if r.WhichOneof("kind") == "points"]
    scene = [batch for batch in batches if batch.designation == 1]
    if not scene or sum(len(batch.points) for batch in scene) == 0:
        failures.append("survey output carries no static-scene points (designation 1)")
    object_batches = [batch for batch in batches if batch.designation >= 100]
    object_points = sum(len(batch.points) for batch in object_batches)
    if object_points < min_object_points:
        failures.append(
            f"survey output carries {object_points} object points, "
            f"expected at least {min_object_points}"
        )
    for batch in batches:
        for point in batch.points:
            if not (math.isfinite(point.x) and math.isfinite(point.y) and math.isfinite(point.z)):
                failures.append(f"frame {batch.frame_id}: non-finite point in survey output")
                return failures
    return failures


def _frame_message(message: survey_pb2.Cm5Request) -> bytes:
    payload = message.SerializeToString()
    return struct.pack(">BI", 0, len(payload)) + payload


def _post_stream(address: str, path: str, requests: list[survey_pb2.Cm5Request]) -> list[bytes]:
    body = b"".join(_frame_message(request) for request in requests)
    connection = http.client.HTTPConnection(address, timeout=120)
    try:
        connection.request(
            "POST", path, body=body, headers={"content-type": "application/connect+proto"}
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


def _config(fixture_dir: Path) -> survey_pb2.Cm5Request:
    calibration = load_calibration(
        PreparedDataset(DATASETS["euroc-v1-01-easy"], fixture_dir, ())
    ).scaled(FRAME_WIDTH, FRAME_HEIGHT)
    return survey_pb2.Cm5Request(
        config=survey_pb2.Cm5StreamConfig(
            calibration=survey_pb2.StereoCalibration(
                calibration_id="euroc-verify",
                focal_length_px=calibration.fx,
                baseline_m=calibration.baseline_m,
                cx=calibration.cx,
                cy=calibration.cy,
                width=FRAME_WIDTH,
                height=FRAME_HEIGHT,
            ),
            video_channels=[],
        )
    )


def measure_backend_fps(backend: SlamBackend, fixture_dir: Path, frame_count: int = 40) -> Rate:
    """Feed recorded stereo pairs to a SLAM backend; posed frames per second.

    This is the RTAB-Map frame rate when the backend is the streaming
    sidecar (`measure_rtabmap_fps`); the count is frames that came back
    with a pose, over the wall time of feeding plus `flush()`.
    """
    timestamps = load_timestamps(fixture_dir, frame_count)
    started = time.perf_counter()
    posed = 0
    for index, t_ns in enumerate(timestamps):
        pair = StereoFramePair(
            frame_id=index + 1,
            t_ns=t_ns,
            left_ref=f"frame-{index + 1}-left",
            right_ref=f"frame-{index + 1}-right",
            calibration_id="euroc-verify",
            left_data=(fixture_dir / "mav0" / "cam0" / "data" / f"{t_ns}.jpg").read_bytes(),
            right_data=(fixture_dir / "mav0" / "cam1" / "data" / f"{t_ns}.jpg").read_bytes(),
        )
        if backend.process_frame(pair).pose is not None:
            posed += 1
    flush = getattr(backend, "flush", None)
    if callable(flush):
        posed = sum(1 for result in flush() if result.pose is not None)
    dropped = int(getattr(backend, "dropped_frames", 0))
    return Rate("rtabmap", posed, time.perf_counter() - started, dropped)


def measure_rtabmap_fps(
    fixture_dir: Path, frame_count: int = 40, native_binary: Path | None = None
) -> Rate:
    """The RTAB-Map streaming sidecar's frame rate on the demo stream.

    Docker by default; with `native_binary`, the natively built
    stream tool on this machine instead (no Docker, no emulation).
    """
    from surmap.survey.cm5_main import streaming_backend

    backend = streaming_backend(fixture_dir, native_binary=native_binary)
    try:
        return measure_backend_fps(backend, fixture_dir, frame_count)
    finally:
        backend.close()


def _frame(fixture_dir: Path, frame_id: int, t_ns: int, channel: int) -> survey_pb2.Cm5Request:
    data = (fixture_dir / "mav0" / f"cam{channel}" / "data" / f"{t_ns}.jpg").read_bytes()
    return survey_pb2.Cm5Request(
        frame=survey_pb2.RawVideoFrame(
            frame_id=frame_id,
            t_ns=t_ns,
            channel=channel,
            width=FRAME_WIDTH,
            height=FRAME_HEIGHT,
            encoding=survey_pb2.FRAME_ENCODING_MJPEG,
            data=data,
        )
    )


def verify(
    address: str,
    fixture_dir: Path,
    frame_count: int = 40,
    *,
    min_frames_with_detections: int = 10,
    min_track_length: int = 3,
    min_object_points: int = 50,
) -> VerifyReport:
    """Feed the demo stream to the server at `address`.

    One check per output stream, plus a frame rate per stream: the
    detections rate is the Coral detector's end-to-end rate (decode,
    inference, tracking, wire), and the survey rate is the server's
    SLAM + stereo pipeline rate on the same frames.
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
                CheckResult("detections", False, "not run: server unreachable"),
                CheckResult("survey", False, "not run: server unreachable"),
            ],
            rates,
        )

    timestamps = load_timestamps(fixture_dir, frame_count)

    detection_requests = [_config(fixture_dir)] + [
        _frame(fixture_dir, index + 1, t_ns, 0) for index, t_ns in enumerate(timestamps)
    ]
    started = time.perf_counter()
    payloads = _post_stream(
        address, "/surmap.survey.v1.Cm5SurveyService/StreamDetections", detection_requests
    )
    rates.append(Rate("coral-detections", len(timestamps), time.perf_counter() - started))
    messages = [survey_pb2.DetectionResponse.FromString(payload).detections for payload in payloads]
    failures = check_detections(
        messages,
        width=FRAME_WIDTH,
        height=FRAME_HEIGHT,
        min_frames_with_detections=min_frames_with_detections,
        min_track_length=min_track_length,
    )
    with_detections = sum(1 for message in messages if message.detections)
    results.append(
        CheckResult(
            "detections",
            not failures,
            failures[0]
            if failures
            else f"{with_detections}/{len(messages)} frames carry tracked detections",
        )
    )

    survey_requests = [_config(fixture_dir)]
    for index, t_ns in enumerate(timestamps):
        survey_requests += [
            _frame(fixture_dir, index + 1, t_ns, 0),
            _frame(fixture_dir, index + 1, t_ns, 1),
        ]
    started = time.perf_counter()
    payloads = _post_stream(
        address, "/surmap.survey.v1.Cm5SurveyService/StreamSurvey", survey_requests
    )
    rates.append(Rate("survey", len(timestamps), time.perf_counter() - started))
    responses = [survey_pb2.Cm5Response.FromString(payload) for payload in payloads]
    failures = check_survey(responses, min_object_points=min_object_points)
    object_points = sum(
        len(r.points.points)
        for r in responses
        if r.WhichOneof("kind") == "points" and r.points.designation >= 100
    )
    results.append(
        CheckResult(
            "survey",
            not failures,
            failures[0] if failures else f"scene points plus {object_points} object points",
        )
    )
    return VerifyReport(results, rates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", nargs="?", help="CM5 server address, e.g. 10.88.77.237:8080")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--frames", type=int, default=40)
    parser.add_argument("--min-detection-frames", type=int, default=10)
    parser.add_argument("--min-track-length", type=int, default=3)
    parser.add_argument("--min-object-points", type=int, default=50)
    parser.add_argument(
        "--rtabmap",
        action="store_true",
        help="also measure the local RTAB-Map streaming sidecar's frame rate (needs Docker)",
    )
    parser.add_argument(
        "--rtabmap-only",
        action="store_true",
        help="measure only the RTAB-Map sidecar's frame rate, with no server: "
        "no Coral detector, no object tracking, no stereo object lifting — "
        "recorded pairs straight into the backend (needs Docker)",
    )
    parser.add_argument(
        "--rtabmap-native",
        type=Path,
        default=None,
        help="measure RTAB-Map with this natively built stream binary "
        "(system RTAB-Map, no Docker; build: scripts/build_rtabmap_native.sh)",
    )
    args = parser.parse_args(argv)
    if args.rtabmap_only:
        rate = measure_rtabmap_fps(args.fixture, args.frames, native_binary=args.rtabmap_native)
        dropped = f", {rate.dropped} dropped" if rate.dropped else ""
        print(
            f"RATE {rate.name}: {rate.fps:.1f} fps "
            f"({rate.frames} frames in {rate.elapsed_s:.2f}s{dropped})"
        )
        return 0
    if not args.address:
        parser.error("address is required unless --rtabmap-only is given")
    report = verify(
        args.address,
        args.fixture,
        args.frames,
        min_frames_with_detections=args.min_detection_frames,
        min_track_length=args.min_track_length,
        min_object_points=args.min_object_points,
    )
    rates = list(report.rates)
    if args.rtabmap:
        rates.append(
            measure_rtabmap_fps(args.fixture, args.frames, native_binary=args.rtabmap_native)
        )
    for result in report.checks:
        print(f"{'PASS' if result.ok else 'FAIL'} {result.name}: {result.detail}")
    for rate in rates:
        print(
            f"RATE {rate.name}: {rate.fps:.1f} fps ({rate.frames} frames in {rate.elapsed_s:.2f}s)"
        )
    return 0 if all(result.ok for result in report.checks) else 1


if __name__ == "__main__":
    sys.exit(main())
