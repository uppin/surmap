#!/usr/bin/env python3
"""Verify a simulated drone's CM5 survey server: `scripts/verify_cm5.py --simulated`.

A simulated drone's CM5 (no Coral, no calibration of its own, e.g. on Modal) gets what its
simulator would send: the fixture's camera definitions in the stream config, a GPS fix with
every pair, then a region query on the same connection while the survey stream is open.
`hold_s` paces the frames so the stream stays open that long. The shared report types,
fixture readers and checks are `verify_cm5`'s.
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verify_cm5 import (  # noqa: E402
    FRAME_HEIGHT,
    FRAME_WIDTH,
    CheckResult,
    Rate,
    VerifyReport,
    _config,
    _frame,
    _health,
    check_survey,
    load_timestamps,
)

from surmap.demo.datasets import scaled_sensor_yaml  # noqa: E402
from surmap.survey.v1 import survey_pb2  # noqa: E402
from surmap.survey.ws_client import SurveyConnection  # noqa: E402

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
        [run.survey_error] if run.survey_error else check_survey(run.responses, min_object_points=0)
    )
    gps_failures = (
        [run.survey_error] if run.survey_error else check_gps(run.responses, run.fixes_sent)
    )
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
