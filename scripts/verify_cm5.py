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
    uv run python scripts/verify_cm5.py wss://<cm5-host>/connect --token <token>

The streams go over the server's Connect WebSocket (`/connect`); the
token defaults to `$SURMAP_SURVEY_TOKEN`.

A simulated drone's CM5 (no Coral, no calibration of its own, e.g. on
Modal) is verified with `--simulated`: the stream brings the fixture's
camera definitions, a GPS fix rides with every pair, and a region query
runs on the same connection while the survey stream is open.
`--hold-s` paces the frames so the stream stays open that long:

    uv run python scripts/verify_cm5.py wss://<cm5-host> --simulated --hold-s 200

To measure the RTAB-Map streaming sidecar alone — no server, no
Coral detector, no object tracking, recorded pairs straight into
the backend (needs Docker):

    uv run python scripts/verify_cm5.py --rtabmap-only [--frames N]

Exits 0 only when every check passes. No target is stored in the
repo: the address is a CLI argument, as with the deploy scripts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
import urllib.request
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from surmap.demo.datasets import (  # noqa: E402
    DATASETS,
    PreparedDataset,
    load_calibration,
    scaled_sensor_yaml,
)
from surmap.slam.base import SlamBackend  # noqa: E402
from surmap.survey.endpoint import survey_token  # noqa: E402
from surmap.survey.v1 import survey_pb2  # noqa: E402
from surmap.survey.ws_client import SurveyConnection, health_url  # noqa: E402
from surmap.types import StereoFramePair  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "euroc_v101_rtabmap"
# Long enough for a serverless host (e.g. Modal) to cold-start the server.
_HEALTH_TIMEOUT_S = 60
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


def _stream_detections(
    address: str, requests: list[survey_pb2.Cm5Request], token: str | None
) -> list[survey_pb2.DetectionResponse]:
    async def run() -> list[survey_pb2.DetectionResponse]:
        async with SurveyConnection.open(address, token=token) as connection:
            return [r async for r in connection.stream_detections(_each(requests))]

    return asyncio.run(run())


def _stream_survey(
    address: str, requests: list[survey_pb2.Cm5Request], token: str | None
) -> list[survey_pb2.Cm5Response]:
    async def run() -> list[survey_pb2.Cm5Response]:
        async with SurveyConnection.open(address, token=token) as connection:
            return [r async for r in connection.stream_survey(_each(requests))]

    return asyncio.run(run())


async def _each(requests: list[survey_pb2.Cm5Request]) -> AsyncIterator[survey_pb2.Cm5Request]:
    for request in requests:
        yield request


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


# Where the simulated drone's GPS track starts (WGS84), and how far it moves per pair.
SIM_ORIGIN = (47.3769, 8.5417, 420.0)
SIM_STEP_DEG = 1e-6
# How long the simulated check waits for the CM5 to pose the frames it sent.
_POSE_WAIT_S = 60.0
# The region the simulated check asks for: the middle of the left image.
_REGION_POLYGON = ((94.0, 60.0), (282.0, 60.0), (282.0, 180.0), (94.0, 180.0))


def _camera_yamls(fixture_dir: Path) -> tuple[str, str]:
    def camera(name: str) -> str:
        text = (fixture_dir / "mav0" / name / "sensor.yaml").read_text(encoding="utf-8")
        return scaled_sensor_yaml(text, FRAME_WIDTH, FRAME_HEIGHT)

    return camera("cam0"), camera("cam1")


def _health(address: str) -> CheckResult:
    try:
        with urllib.request.urlopen(health_url(address), timeout=_HEALTH_TIMEOUT_S) as response:
            status = int(response.status)  # type: ignore[attr-defined]
        return CheckResult("health", status == 200, f"GET /health/is_alive -> {status}")
    except Exception as exc:  # a dead server fails every later check too
        return CheckResult("health", False, f"GET /health/is_alive failed: {exc}")


@dataclass
class _SimulatedRun:
    responses: list[survey_pb2.Cm5Response]
    regions: list[survey_pb2.RegionPoints]
    fixes_sent: int
    survey_error: str
    region_error: str
    elapsed_s: float


async def _simulated_run(
    address: str, fixture_dir: Path, frame_count: int, token: str | None, hold_s: float
) -> _SimulatedRun:
    timestamps = load_timestamps(fixture_dir, frame_count)
    cam0, cam1 = _camera_yamls(fixture_dir)
    config = _config(fixture_dir)
    config.config.cam0_yaml, config.config.cam1_yaml = cam0, cam1
    pace_s = hold_s / max(1, len(timestamps))
    responses: list[survey_pb2.Cm5Response] = []
    regions: list[survey_pb2.RegionPoints] = []
    region_error = ""
    survey_error = ""
    frames_sent = asyncio.Event()
    all_anchored = asyncio.Event()
    region_done = asyncio.Event()

    async def requests() -> AsyncIterator[survey_pb2.Cm5Request]:
        yield config
        for index, t_ns in enumerate(timestamps):
            yield _frame(fixture_dir, index + 1, t_ns, 0)
            yield _frame(fixture_dir, index + 1, t_ns, 1)
            lat, lon, alt = SIM_ORIGIN
            yield survey_pb2.Cm5Request(
                gps=survey_pb2.GpsFix(
                    t_ns=t_ns,
                    lat=lat + index * SIM_STEP_DEG,
                    lon=lon + index * SIM_STEP_DEG,
                    alt_m=alt,
                    accuracy_m=1.5,
                )
            )
            if pace_s > 0:
                await asyncio.sleep(pace_s)
        frames_sent.set()
        # Keep the survey stream (and the stream's backend) open for the region query.
        await region_done.wait()

    def latest_posed_frame() -> int:
        # The last fix is anchored only once a pose at or after it has landed: its frame is
        # one the CM5 has posed and still holds.
        anchored = [
            r.gps_anchor.frame_id
            for r in responses
            if r.WhichOneof("kind") == "gps_anchor" and r.gps_anchor.HasField("frame_id")
        ]
        if anchored:
            return anchored[-1]
        posed = [r.odom.frame_id for r in responses if r.WhichOneof("kind") == "odom"]
        posed += [
            r.points.frame_id
            for r in responses
            if r.WhichOneof("kind") == "points" and r.points.designation == 1
        ]
        return max(posed, default=len(timestamps))

    started = time.perf_counter()
    async with SurveyConnection.open(address, token=token) as connection:

        async def survey() -> None:
            nonlocal survey_error
            try:
                async for response in connection.stream_survey(requests()):
                    responses.append(response)
                    anchors = sum(1 for r in responses if r.WhichOneof("kind") == "gps_anchor")
                    if anchors >= len(timestamps):
                        all_anchored.set()
            except Exception as exc:
                survey_error = f"StreamSurvey failed: {exc}"
                frames_sent.set()
                all_anchored.set()

        async def query() -> AsyncIterator[survey_pb2.RegionQuery]:
            yield survey_pb2.RegionQuery(
                query_id=1,
                frame_id=latest_posed_frame(),
                channel=0,
                width=FRAME_WIDTH,
                height=FRAME_HEIGHT,
                polygon=[survey_pb2.Point2(x=x, y=y) for x, y in _REGION_POLYGON],
            )

        surveying = asyncio.create_task(survey())
        await frames_sent.wait()
        try:
            await asyncio.wait_for(all_anchored.wait(), _POSE_WAIT_S)
        except TimeoutError:
            pass  # queried anyway, on the latest frame the CM5 did pose
        try:
            regions = [r async for r in connection.stream_region_points(query())]
        except Exception as exc:
            region_error = f"StreamRegionPoints failed: {exc}"
        finally:
            region_done.set()
        await surveying
    return _SimulatedRun(
        responses,
        regions,
        len(timestamps),
        survey_error,
        region_error,
        time.perf_counter() - started,
    )


def check_gps(responses: list[survey_pb2.Cm5Response], fixes_sent: int) -> list[str]:
    anchors = [r.gps_anchor for r in responses if r.WhichOneof("kind") == "gps_anchor"]
    failures: list[str] = []
    if len(anchors) != fixes_sent:
        failures.append(f"{len(anchors)} GPS anchors for {fixes_sent} fixes sent")
    if not any(anchor.HasField("map_position") for anchor in anchors):
        failures.append("no GPS fix was anchored to a posed frame")
    return failures


def check_regions(regions: list[survey_pb2.RegionPoints]) -> list[str]:
    if not regions:
        return ["the region query got no answer"]
    status = regions[-1].status
    if status != survey_pb2.REGION_STATUS_OK:
        return [f"region query answered {survey_pb2.RegionStatus.Name(status)}"]
    if not any(region.points for region in regions):
        return ["region query answered OK with no points"]
    return []


def verify_simulated(
    address: str,
    fixture_dir: Path,
    frame_count: int = 40,
    *,
    token: str | None = None,
    hold_s: float = 0.0,
) -> VerifyReport:
    """Feed the demo stream to a simulated drone's CM5 at `address`, as its simulator would:
    camera definitions in the stream config, a GPS fix with every pair, then a region query on
    the same connection while the survey stream is still open. `hold_s` paces the frames so
    the stream lasts at least that long."""
    health = _health(address)
    if not health.ok:
        return VerifyReport(
            [health]
            + [
                CheckResult(name, False, "not run: server unreachable")
                for name in ("survey", "gps", "regions")
            ],
            [],
        )
    run = asyncio.run(_simulated_run(address, fixture_dir, frame_count, token, hold_s))
    survey_failures = (
        [run.survey_error]
        if run.survey_error
        else check_survey(run.responses, min_object_points=0)
    )
    gps_failures = [run.survey_error] if run.survey_error else check_gps(run.responses, run.fixes_sent)
    region_failures = [run.region_error] if run.region_error else check_regions(run.regions)
    anchored = sum(
        1
        for r in run.responses
        if r.WhichOneof("kind") == "gps_anchor" and r.gps_anchor.HasField("map_position")
    )
    region_points = sum(len(region.points) for region in run.regions)
    checks = [
        health,
        CheckResult(
            "survey",
            not survey_failures,
            survey_failures[0]
            if survey_failures
            else f"scene points over a {run.elapsed_s:.0f} s stream",
        ),
        CheckResult(
            "gps",
            not gps_failures,
            gps_failures[0] if gps_failures else f"{anchored}/{run.fixes_sent} fixes anchored",
        ),
        CheckResult(
            "regions",
            not region_failures,
            region_failures[0] if region_failures else f"{region_points} points in the region",
        ),
    ]
    return VerifyReport(checks, [Rate("survey", run.fixes_sent, run.elapsed_s)])


def verify(
    address: str,
    fixture_dir: Path,
    frame_count: int = 40,
    *,
    min_frames_with_detections: int = 10,
    min_track_length: int = 3,
    min_object_points: int = 50,
    token: str | None = None,
) -> VerifyReport:
    """Feed the demo stream to the server at `address` (see `connect_url`).

    One check per output stream, plus a frame rate per stream: the
    detections rate is the Coral detector's end-to-end rate (decode,
    inference, tracking, wire), and the survey rate is the server's
    SLAM + stereo pipeline rate on the same frames.
    """
    results: list[CheckResult] = []
    rates: list[Rate] = []
    try:
        with urllib.request.urlopen(health_url(address), timeout=_HEALTH_TIMEOUT_S) as response:
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
    try:
        detection_responses = _stream_detections(address, detection_requests, token)
        stream_error = ""
    except Exception as exc:  # the server refused or broke the stream: the check fails
        detection_responses, stream_error = [], f"StreamDetections failed: {exc}"
    rates.append(Rate("coral-detections", len(timestamps), time.perf_counter() - started))
    messages = [response.detections for response in detection_responses]
    failures = (
        [stream_error]
        if stream_error
        else check_detections(
            messages,
            width=FRAME_WIDTH,
            height=FRAME_HEIGHT,
            min_frames_with_detections=min_frames_with_detections,
            min_track_length=min_track_length,
        )
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
    try:
        responses = _stream_survey(address, survey_requests, token)
        stream_error = ""
    except Exception as exc:  # the server refused or broke the stream: the check fails
        responses, stream_error = [], f"StreamSurvey failed: {exc}"
    rates.append(Rate("survey", len(timestamps), time.perf_counter() - started))
    failures = (
        [stream_error]
        if stream_error
        else check_survey(responses, min_object_points=min_object_points)
    )
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
    parser.add_argument(
        "address",
        nargs="?",
        help="CM5 server: host:port, or a ws(s):// / http(s):// URL, e.g. 10.88.77.237:8080",
    )
    parser.add_argument(
        "--token", default=None, help="bearer token (default: $SURMAP_SURVEY_TOKEN)"
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--frames", type=int, default=40)
    parser.add_argument("--min-detection-frames", type=int, default=10)
    parser.add_argument("--min-track-length", type=int, default=3)
    parser.add_argument("--min-object-points", type=int, default=50)
    parser.add_argument(
        "--simulated",
        action="store_true",
        help="verify a simulated drone's CM5: cameras and GPS over RPC, region points, no Coral",
    )
    parser.add_argument(
        "--hold-s",
        type=float,
        default=0.0,
        help="with --simulated, pace the frames so the survey stream stays open this long",
    )
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
    if args.simulated:
        report = verify_simulated(
            args.address,
            args.fixture,
            args.frames,
            token=survey_token(args.token),
            hold_s=args.hold_s,
        )
        return _print_report(report)
    report = verify(
        args.address,
        args.fixture,
        args.frames,
        min_frames_with_detections=args.min_detection_frames,
        min_track_length=args.min_track_length,
        min_object_points=args.min_object_points,
        token=survey_token(args.token),
    )
    rates = list(report.rates)
    if args.rtabmap:
        rates.append(
            measure_rtabmap_fps(args.fixture, args.frames, native_binary=args.rtabmap_native)
        )
    return _print_report(VerifyReport(report.checks, rates))


def _print_report(report: VerifyReport) -> int:
    for result in report.checks:
        print(f"{'PASS' if result.ok else 'FAIL'} {result.name}: {result.detail}")
    for rate in report.rates:
        print(
            f"RATE {rate.name}: {rate.fps:.1f} fps ({rate.frames} frames in {rate.elapsed_s:.2f}s)"
        )
    return 0 if all(result.ok for result in report.checks) else 1


if __name__ == "__main__":
    sys.exit(main())
