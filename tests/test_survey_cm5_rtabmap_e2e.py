"""Real RTAB-Map e2e: EuRoC pairs through the real CM5 server, with
pose and scene points from the real RTAB-Map Docker sidecar.

Nothing is installed on the host: `scripts/fetch_rtabmap_fixture.py`
pulls the pinned sidecar image and cuts the EuRoC subset. Without
that preparation this test skips (or fails, when
`SURMAP_REQUIRE_RTABMAP_E2E=1`, as CI sets after running the script).
The server and the sidecar are both closed after the run, pass or
fail.
"""

import asyncio
import json
import math
import os
import pathlib
import re
import shutil
import urllib.error

import pytest

from surmap.survey.cm5_main import build_description, sidecar_backend
from surmap.survey.v1 import survey_pb2
from tests.test_survey_server_e2e import _connect_bidi, _get_status, running_server

FIXTURE = (
    pathlib.Path(os.environ.get("SURMAP_EUROC_FIXTURE", ""))
    if os.environ.get("SURMAP_EUROC_FIXTURE")
    else pathlib.Path(__file__).parent / "fixtures" / "euroc_v101_rtabmap"
)
REQUIRED = os.environ.get("SURMAP_REQUIRE_RTABMAP_E2E") == "1"


def _require_prepared() -> dict[str, object]:
    manifest = FIXTURE / "manifest.json"
    if not manifest.is_file() or shutil.which("docker") is None:
        message = (
            "RTAB-Map e2e not prepared: run "
            "`uv run python scripts/fetch_rtabmap_fixture.py` first "
            "(pulls the pinned sidecar image and cuts the EuRoC subset)"
        )
        if REQUIRED:
            pytest.fail(message)
        pytest.skip(message)
    loaded: dict[str, object] = json.loads(manifest.read_text(encoding="utf-8"))
    return loaded


def _calibration() -> tuple[float, float, float, float, float]:
    """(fx, cx, cy, baseline_m, width) from the fixture's cam0/cam1 yaml."""
    translations = []
    intrinsics: list[float] = []
    for channel in (0, 1):
        text = (FIXTURE / "mav0" / f"cam{channel}" / "sensor.yaml").read_text(encoding="utf-8")
        data_match = re.search(r"data: \[([^\]]+)\]", text)
        assert data_match is not None
        data = [float(value) for value in data_match.group(1).split(",")]
        translations.append((data[3], data[7], data[11]))
        if channel == 0:
            intrinsics_match = re.search(r"intrinsics: \[([^\]]+)\]", text)
            assert intrinsics_match is not None
            intrinsics = [float(value) for value in intrinsics_match.group(1).split(",")]
    baseline = math.dist(translations[0], translations[1])
    return intrinsics[0], intrinsics[2], intrinsics[3], baseline, 376.0


def _requests(manifest: dict[str, object]) -> list[survey_pb2.Cm5Request]:
    fx, cx, cy, baseline, _ = _calibration()
    requests: list[survey_pb2.Cm5Request] = [
        survey_pb2.Cm5Request(
            config=survey_pb2.Cm5StreamConfig(
                calibration=survey_pb2.StereoCalibration(
                    calibration_id="euroc-v1-01-sidecar",
                    focal_length_px=fx,
                    baseline_m=baseline,
                    cx=cx,
                    cy=cy,
                    width=376,
                    height=240,
                ),
                video_channels=[],
            )
        )
    ]
    timestamps = manifest["frame_timestamps_ns"]
    assert isinstance(timestamps, list)
    for index, t_ns in enumerate(timestamps):
        for channel in (0, 1):
            data = (FIXTURE / "mav0" / f"cam{channel}" / "data" / f"{t_ns}.jpg").read_bytes()
            requests.append(
                survey_pb2.Cm5Request(
                    frame=survey_pb2.RawVideoFrame(
                        frame_id=index + 1,
                        t_ns=int(t_ns),
                        channel=channel,
                        width=376,
                        height=240,
                        encoding=survey_pb2.FRAME_ENCODING_MJPEG,
                        data=data,
                    )
                )
            )
    return requests


async def test_euroc_pairs_stream_real_rtabmap_poses_and_points() -> None:
    manifest = _require_prepared()
    backend = sidecar_backend(FIXTURE)
    try:
        # Given the real CM5 server backed by the real RTAB-Map sidecar
        async with running_server(build_description(slam=backend, use_stereo=False)) as address:
            # When the EuRoC pairs stream through over the wire (the
            # sidecar runs RTAB-Map when the stream ends)
            payloads = await asyncio.to_thread(
                _connect_bidi,
                address,
                "/surmap.survey.v1.Cm5SurveyService/StreamSurvey",
                _requests(manifest),
            )
            assert await asyncio.to_thread(_get_status, address, "/health/is_alive") == 200
    finally:
        backend.close()

    # Then the server is closed after the run
    with pytest.raises(urllib.error.URLError):
        _get_status(address, "/health/is_alive")

    responses = [survey_pb2.Cm5Response.FromString(p) for p in payloads]
    batches = [r.points for r in responses if r.WhichOneof("kind") == "points"]

    # And the streamed scene is RTAB-Map's: designated scene batches
    # with many real points, on several keyframes, in a spread-out map
    assert backend.closed
    assert batches, "no point batches streamed from the RTAB-Map sidecar"
    assert all(batch.designation == 1 for batch in batches)
    total_points = sum(len(batch.points) for batch in batches)
    assert total_points > 10_000
    assert all(
        math.isfinite(point.x) and math.isfinite(point.y) and math.isfinite(point.z)
        for batch in batches
        for point in batch.points
    )
    xs = [point.x for batch in batches for point in batch.points]
    ys = [point.y for batch in batches for point in batch.points]
    assert max(xs) - min(xs) > 0.5
    assert max(ys) - min(ys) > 0.5

    # And RTAB-Map really moved: several optimized poses, travelling
    trajectory = backend.trajectory()
    assert len(trajectory) >= 3
    travelled = max(
        math.dist(
            (pose.position.x, pose.position.y, pose.position.z),
            (trajectory[0].position.x, trajectory[0].position.y, trajectory[0].position.z),
        )
        for pose in trajectory
    )
    assert travelled > 0.3
