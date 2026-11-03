"""Acceptance: the committed Bevy capture, streamed through the real sidecar.

Mirrors tests/test_slam_streaming_e2e.py's docker/image skip, except that
the capture fixture itself must exist: it is committed with this feature,
so a missing fixture fails (and always fails when
SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1 turns the image skips into failures).
The sidecar runs once for the whole module.
"""

import os
import pathlib
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pytest

from surmap.simulation.bevy_capture import BevyCapture, load_bevy_capture
from surmap.simulation.bevy_ground_truth import project_box
from surmap.simulation.bevy_wire import GroundTruthBox
from surmap.simulation.calibration import render_cam_sensor_yaml
from surmap.simulation.trajectory_eval import align_rigid, ate_rmse
from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.slam.streaming import StreamingRtabmapBackend, stream_image_tag
from surmap.types import Vec3

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "bevy_sim_capture"
REQUIRED = os.environ.get("SURMAP_REQUIRE_RTABMAP_STREAM_E2E") == "1"


def _require_prepared() -> None:
    if not FIXTURE.is_dir():
        pytest.fail(
            "Bevy capture fixture is missing: record it with the native recorder "
            "into tests/fixtures/bevy_sim_capture/ (changeset M7)"
        )
    tag = stream_image_tag()
    docker = shutil.which("docker")
    image_ready = False
    if docker is not None:
        image = subprocess.run([docker, "image", "inspect", tag], capture_output=True, text=True)
        image_ready = image.returncode == 0
    if docker is None or not image_ready:
        message = (
            "streaming e2e not prepared: run `uv run python scripts/build_rtabmap_stream.py` first"
        )
        if REQUIRED:
            pytest.fail(message)
        pytest.skip(message)


def _positions(vectors: list[Vec3]) -> np.ndarray:
    return np.array([[v.x, v.y, v.z] for v in vectors], dtype=np.float64)


def _polygon_area(polygon: tuple[tuple[float, float], ...]) -> float:
    return (
        abs(
            sum(
                x1 * y2 - x2 * y1
                for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True)
            )
        )
        / 2.0
    )


@dataclass
class StreamedCapture:
    capture: BevyCapture
    backend: StreamingRtabmapBackend
    posed_frame_ids: tuple[int, ...]
    estimated_positions: np.ndarray
    truth_positions: np.ndarray
    graph_pose_count: int
    region_frame_id: int
    region_box: GroundTruthBox | None
    region_result: RegionResult


@pytest.fixture(scope="module")
def streamed() -> Iterator[StreamedCapture]:
    _require_prepared()
    capture = load_bevy_capture(FIXTURE)
    calibration = capture.calibration
    backend = StreamingRtabmapBackend(
        cam0_yaml=render_cam_sensor_yaml(calibration, 0),
        cam1_yaml=render_cam_sensor_yaml(calibration, 1),
        width=calibration.width,
        height=calibration.height,
    )
    try:
        for frame in capture.frames:
            backend.process_frame(frame.pair)
            backend.poll_updates()
        truth_by_frame = {frame.pair.frame_id: frame.pose_enu.position for frame in capture.frames}
        posed_before_flush: list[int] = []
        for frame in capture.frames:
            odometry = backend.frame_odometry(frame.pair.frame_id)
            if odometry is not None and odometry.pose is not None:
                posed_before_flush.append(frame.pair.frame_id)
        recent_id = posed_before_flush[-1]
        recent = next(frame for frame in capture.frames if frame.pair.frame_id == recent_id)
        candidates: list[tuple[float, GroundTruthBox, tuple[tuple[float, float], ...]]] = []
        for candidate_box in capture.objects:
            candidate_polygon = project_box(candidate_box, recent.pose_enu, calibration)
            if len(candidate_polygon) >= 3 and all(
                0.0 <= x <= calibration.width and 0.0 <= y <= calibration.height
                for x, y in candidate_polygon
            ):
                candidates.append(
                    (_polygon_area(candidate_polygon), candidate_box, candidate_polygon)
                )
        if candidates:
            _, region_box, polygon = max(candidates, key=lambda candidate: candidate[0])
        else:
            region_box = None
            polygon = project_box(capture.objects[0], recent.pose_enu, calibration)
        region_result = backend.region_points(
            RegionQuery(
                query_id=1,
                frame_id=recent_id,
                channel=0,
                width=calibration.width,
                height=calibration.height,
                polygon=polygon,
            )
        )
        # flush() returns only once the sidecar sends its final graph.
        results = backend.flush()
        backend.poll_updates()
        posed_results = [
            (result.frame_id, result.pose) for result in results if result.pose is not None
        ]
        estimated = _positions([pose.position for _, pose in posed_results])
        truth = _positions([truth_by_frame[frame_id] for frame_id, _ in posed_results])
        context = StreamedCapture(
            capture=capture,
            backend=backend,
            posed_frame_ids=tuple(frame_id for frame_id, _ in posed_results),
            estimated_positions=estimated,
            truth_positions=truth,
            graph_pose_count=len(backend.trajectory()),
            region_frame_id=recent_id,
            region_box=region_box,
            region_result=region_result,
        )
        yield context
    finally:
        backend.close()


def test_the_sidecar_tracks_the_capture_and_builds_a_sparse_map(
    streamed: StreamedCapture,
) -> None:
    # Given the committed Bevy capture streamed through the real sidecar (module fixture)
    total = len(streamed.capture.frames)

    # When its trajectory is aligned rigidly onto the ground-truth rig positions
    alignment = align_rigid(streamed.estimated_positions, streamed.truth_positions)
    ate = ate_rmse(alignment.apply(streamed.estimated_positions), streamed.truth_positions)

    # Then PRD criterion 1 holds: posed share, ATE, keyframes, final graph, map size
    assert len(streamed.posed_frame_ids) / total >= 0.90
    assert ate <= 0.5
    assert streamed.backend.keyframe_count >= 3
    assert streamed.graph_pose_count >= 3
    assert len(streamed.backend.map_snapshot()) >= 2000


def test_a_polygon_around_a_ground_truth_object_returns_its_dense_points(
    streamed: StreamedCapture,
) -> None:
    # Given the region answer for a ground-truth object on a recent frame (module fixture)
    result = streamed.region_result
    box = streamed.region_box

    # When the returned map-frame points are aligned into ENU
    alignment = align_rigid(streamed.estimated_positions, streamed.truth_positions)
    points = alignment.apply(_positions(list(result.points)))

    # Then a ground-truth object was fully framed, and PRD criterion 2 holds:
    # ok, enough points, almost all inside the grown box
    assert box is not None
    grown_min = np.array([box.min_enu.x - 0.5, box.min_enu.y - 0.5, box.min_enu.z - 0.5])
    grown_max = np.array([box.max_enu.x + 0.5, box.max_enu.y + 0.5, box.max_enu.z + 0.5])
    inside = np.all((points >= grown_min) & (points <= grown_max), axis=1)
    assert result.status is RegionStatus.OK
    assert len(result.points) >= 200
    assert float(np.mean(inside)) >= 0.80
