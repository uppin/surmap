"""Real-container streaming e2e over the 90-pair EuRoC fixture.

Skips when the derived image or fixture is absent; fails when
SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1 (CI sets it after building).
"""

import json
import math
import os
import pathlib
import shutil
import subprocess
import time

import numpy as np
import pytest

from surmap.demo.datasets import scaled_sensor_yaml
from surmap.slam.stream_protocol import OdomUpdate
from surmap.slam.streaming import StreamingRtabmapBackend, stream_image_tag
from surmap.types import StereoFramePair

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "euroc_v101_rtabmap"
REQUIRED = os.environ.get("SURMAP_REQUIRE_RTABMAP_STREAM_E2E") == "1"


def _require_prepared() -> dict[str, object]:
    manifest = FIXTURE / "manifest.json"
    tag = stream_image_tag()
    docker = shutil.which("docker")
    image_ready = False
    if docker is not None:
        image = subprocess.run([docker, "image", "inspect", tag], capture_output=True, text=True)
        image_ready = image.returncode == 0
    if not manifest.is_file() or docker is None or not image_ready:
        message = (
            "streaming e2e not prepared: run `uv run python scripts/fetch_rtabmap_fixture.py` "
            "and `uv run python scripts/build_rtabmap_stream.py` first"
        )
        if REQUIRED:
            pytest.fail(message)
        pytest.skip(message)
    loaded: dict[str, object] = json.loads(manifest.read_text(encoding="utf-8"))
    return loaded


def test_streaming_backend_maps_live_over_the_fixture() -> None:
    manifest = _require_prepared()
    timestamps = manifest["frame_timestamps_ns"]
    assert isinstance(timestamps, list)
    cam0 = (FIXTURE / "mav0" / "cam0" / "sensor.yaml").read_text(encoding="utf-8")
    cam1 = (FIXTURE / "mav0" / "cam1" / "sensor.yaml").read_text(encoding="utf-8")
    backend = StreamingRtabmapBackend(
        cam0_yaml=scaled_sensor_yaml(cam0, 376, 240),
        cam1_yaml=scaled_sensor_yaml(cam1, 376, 240),
    )
    live_updates = 0
    tracked_keypoints: list[int] = []
    map_poses = 0
    try:
        for index, t_ns in enumerate(timestamps):
            backend.process_frame(
                StereoFramePair(
                    frame_id=index + 1,
                    t_ns=int(t_ns),
                    left_ref=str(FIXTURE / "mav0" / "cam0" / "data" / f"{t_ns}.jpg"),
                    right_ref=str(FIXTURE / "mav0" / "cam1" / "data" / f"{t_ns}.jpg"),
                    calibration_id="euroc-v1-01-stream",
                )
            )
            updates = backend.poll_updates()  # live, before stdin closes
            live_updates += len(updates)
            tracked_keypoints += [
                len(update.keypoints) for update in updates if isinstance(update, OdomUpdate)
            ]
            map_poses += sum(
                1 for u in updates if isinstance(u, OdomUpdate) and u.map_pose is not None
            )
            # Real-time feed at the recording's 20 Hz: the backend drops
            # the oldest pairs when fed faster than RTAB-Map runs.
            time.sleep(1 / 20)
        assert live_updates > 0, "no odometry arrived before flush (batch, not live)"
        results = backend.flush()
        keyframes = backend.keyframe_count
        rectification = backend.rectification
        cloud = backend.map_cloud()
    finally:
        backend.close()

    assert backend.live_containers == ()
    leftover = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"name={backend.container_name}",
            "--format",
            "{{.Names}}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.strip()
    assert leftover == ""
    trajectory = backend.trajectory()
    assert len(trajectory) >= 3
    travelled = max(
        math.dist(
            (p.position.x, p.position.y, p.position.z),
            (trajectory[0].position.x, trajectory[0].position.y, trajectory[0].position.z),
        )
        for p in trajectory
    )
    assert travelled > 0.3
    assert results and len(results[-1].static_points) > 5_000
    # Only nodes RTAB-Map's graph kept are keyframes
    assert keyframes == len(trajectory)
    # Each frame's odometry carries the features it tracked, and the
    # rectification to place them on the raw image came with ready
    assert tracked_keypoints and sorted(tracked_keypoints)[len(tracked_keypoints) // 2] > 50
    assert rectification is not None and rectification.raw[0] > 0
    # Each tracked frame also carries its pose after the map correction
    assert map_poses > 0
    # Points carry the camera's real intensity, not one flat colour
    assert len(np.unique(cloud.colors[:, 0])) > 50
