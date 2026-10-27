"""KITTI stereo E2E: real stereo + real RTAB-Map + moving pipeline.

The full retrospective chain on recorded data (design 6.2):
KITTI tracking sequence 0020 frames are staged into the real
`SidecarRtabmapBackend`; its flush gives real keyframe poses;
the posed keyframes are reconstructed with the real
`StereoReconstructor`, transformed by those poses, differenced
against a static layer, and graduated tracks must produce
map-frame snapshots near labelled car positions.

Two findings shape the assembly (recorded in the n5 changeset):

- RTAB-Map's exported assembled cloud is near-empty at driving
  depths (56 points over this segment, independent of export
  depth/decimation), so the static layer is seeded from the
  segment itself: voxels observed by at least two distinct
  keyframes are static (a mover crosses a voxel once), plus
  whatever cloud RTAB did export.
- Depth shells from integer disparity metres wide at this range
  made differencing impossible; the reconstructor's subpixel
  refinement (PR #25) and a wider matching width are what let
  static points repeat across keyframes.

Requires the snippet cache (scripts/fetch_moving_snippets.py
--snippet kitti-tracking-stereo --sequence 0020 --frames 0-119,
plus calib.txt/labels.txt staged alongside). Skipped unless the
cache is present; fails when SURMAP_REQUIRE_KITTI_E2E=1 and it
is not.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest
from PIL import Image

from surmap.geometry import centroid, to_map_frame
from surmap.moving.areas import AreaTracker, areas_from_clusters
from surmap.moving.buffer import Observation, ObservationBuffer
from surmap.moving.classify import TrackMotionStats, Verdict, VerdictMachine
from surmap.moving.config import MovingConfig
from surmap.moving.differencing import StaticLayer
from surmap.moving.keypoints import select_keypoints
from surmap.moving.placement import build_snapshot, object_track_id
from surmap.moving.snippets import _projection, kitti_baseline_m, kitti_sensor_yaml
from surmap.slam.sidecar import SidecarRtabmapBackend
from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.types import StereoFramePair, Vec3

_SNIPPET = (
    Path(
        os.environ.get(
            "SURMAP_SNIPPET_CACHE_DIR",
            str(Path.home() / ".cache" / "surmap" / "moving-snippets"),
        )
    )
    / "kitti-tracking-stereo"
    / "0020"
)
_REQUIRED = os.environ.get("SURMAP_REQUIRE_KITTI_E2E", "") == "1"
_MAX_FRAMES = 80
_VOXEL_M = 0.5


def _snippet_ready() -> bool:
    left = sorted((_SNIPPET / "image_02").glob("*.png")) if _SNIPPET.exists() else []
    return (
        len(left) >= 60 and (_SNIPPET / "calib.txt").exists() and (_SNIPPET / "labels.txt").exists()
    )


CarBox = tuple[int, Vec3, tuple[float, float, float], float]


def _cars(frame_index: int) -> list[CarBox]:
    """Labelled cars on one frame: (track_id, centre, (h, w, l), rotation_y).

    KITTI tracking labels carry dimensions at fields 10-12 and the
    bottom-face-centre location at 13-15; the centre is half the
    height above the location.
    """
    cars: list[CarBox] = []
    for line in (_SNIPPET / "labels.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if int(parts[0]) != frame_index or parts[2] not in ("Car", "Van"):
            continue
        height, width, length = float(parts[10]), float(parts[11]), float(parts[12])
        x, y, z = float(parts[13]), float(parts[14]), float(parts[15])
        centre = Vec3(x, y - height / 2.0, z)
        cars.append((int(parts[1]), centre, (height, width, length), float(parts[16])))
    return cars


def _points_in_car(points: tuple[Vec3, ...], car: CarBox) -> int:
    """Stereo points inside a labelled car's 3D box (camera frame)."""
    _track_id, centre, (height, width, length), rotation_y = car
    cos_r, sin_r = math.cos(-rotation_y), math.sin(-rotation_y)
    count = 0
    for point in points:
        dx, dz = point.x - centre.x, point.z - centre.z
        local_x = cos_r * dx - sin_r * dz
        local_z = sin_r * dx + cos_r * dz
        if (
            abs(local_x) <= length / 2.0 + 0.3
            and abs(local_z) <= width / 2.0 + 0.3
            and abs(point.y - centre.y) <= height / 2.0 + 0.3
        ):
            count += 1
    return count


def test_kitti_stereo_e2e() -> None:
    if not _snippet_ready():
        if _REQUIRED:
            pytest.fail(f"KITTI snippet cache incomplete at {_SNIPPET}")
        pytest.skip("KITTI snippet cache not fetched")
    left_paths = sorted((_SNIPPET / "image_02").glob("*.png"))[:_MAX_FRAMES]
    calib_text = (_SNIPPET / "calib.txt").read_text(encoding="utf-8")
    p2 = _projection(calib_text, "P2")
    baseline = kitti_baseline_m(calib_text)
    with Image.open(left_paths[0]) as image:
        width, height = image.size
    cam0_yaml = kitti_sensor_yaml(calib_text, width, height)
    cam1_yaml = cam0_yaml.replace(
        "data: [1.0, 0.0, 0.0, 0.0,",
        f"data: [1.0, 0.0, 0.0, {baseline},",
    )

    backend = SidecarRtabmapBackend(cam0_yaml=cam0_yaml, cam1_yaml=cam1_yaml)
    try:
        for index, left_path in enumerate(left_paths):
            right_path = _SNIPPET / "image_03" / left_path.name
            t_ns = 1_700_000_000_000_000_000 + index * 100_000_000
            backend.process_frame(
                StereoFramePair(
                    index, t_ns, "", "", "kitti", left_path.read_bytes(), right_path.read_bytes()
                )
            )
        results = backend.flush()
    finally:
        backend.close()

    posed = {r.frame_id: r.pose for r in results if r.pose is not None}
    cloud = [point for r in results for point in r.static_points]
    ordered_poses = [posed[k] for k in sorted(posed)]
    trajectory_m = sum(
        (b.position - a.position).norm()
        for a, b in zip(ordered_poses, ordered_poses[1:], strict=False)
    )
    print(
        f"KITTI E2E: {len(posed)} keyframe poses, trajectory "
        f"{trajectory_m:.1f} m, RTAB exported cloud={len(cloud)} points"
    )
    assert len(posed) >= 6, "RTAB posed too few keyframes"
    assert trajectory_m >= 15.0, "RTAB trajectory implausibly short"

    # Reconstruct only the posed keyframes, at a matching width
    # whose depth shells are fine enough for differencing.
    rig = StereoRig(fx=p2[0], fy=p2[5], cx=p2[2], cy=p2[6], baseline_m=baseline)
    stereo = StereoReconstructor(max_depth_m=40.0, max_disparity=256, match_width_px=400)
    match_scale = max(1, width // 400)
    frames: dict[int, tuple[Vec3, ...]] = {}
    for index in sorted(posed):
        left_path = left_paths[index]
        right_path = _SNIPPET / "image_03" / left_path.name
        frames[index] = stereo.reconstruct(
            FrameImage(width, height, "mjpeg", left_path.read_bytes()),
            FrameImage(width, height, "mjpeg", right_path.read_bytes()),
            rig,
        )

    # The labelled cars are really reconstructed: the best-covered
    # car carries a body of stereo points on some keyframe (near
    # cars measure 13-17 in-box points; smooth car bodywork and
    # truncation at close range cap what matching can see).
    best_car_points = max(
        _points_in_car(frames[index], car) for index in sorted(posed) for car in _cars(index)
    )
    print(f"KITTI E2E: best labelled-car point count {best_car_points}")
    assert best_car_points >= 10, "labelled cars are not reconstructed"

    config = MovingConfig(
        focal_px=p2[0] / match_scale,
        baseline_m=baseline,
        min_cluster_points=10,
        voxel_size_m=_VOXEL_M,
        tau_depth_k=0.3,
    )
    layer = StaticLayer(config)
    layer.seed(cloud)
    # Static seed: voxel centres observed by at least two distinct
    # keyframes (movers cross a voxel only once).
    hit_counts: dict[tuple[int, int, int], int] = {}
    map_frames: dict[int, tuple[Vec3, ...]] = {}
    for index in sorted(posed):
        map_points = tuple(to_map_frame(point, posed[index]) for point in frames[index])
        map_frames[index] = map_points
        keys = {
            (
                math.floor(point.x / _VOXEL_M),
                math.floor(point.y / _VOXEL_M),
                math.floor(point.z / _VOXEL_M),
            )
            for point in map_points
        }
        for key in keys:
            hit_counts[key] = hit_counts.get(key, 0) + 1
    layer.seed(
        Vec3((kx + 0.5) * _VOXEL_M, (ky + 0.5) * _VOXEL_M, (kz + 0.5) * _VOXEL_M)
        for (kx, ky, kz), hits in hit_counts.items()
        if hits >= 2
    )

    tracker = AreaTracker(config)
    stats = TrackMotionStats()
    verdicts = VerdictMachine(config)
    buffer = ObservationBuffer()
    snapshots: list[tuple[int, Vec3]] = []
    graduated_tracks: set[int] = set()
    car_proximate_keyframes = 0
    for index in sorted(posed):
        clusters = layer.difference(index, index * 100_000_000, map_frames[index])
        cars = _cars(index)
        if any(
            (centroid(cluster.points) - to_map_frame(car[1], posed[index])).norm() <= 4.0
            for cluster in clusters
            for car in cars
        ):
            car_proximate_keyframes += 1
        for cluster, observation in zip(clusters, areas_from_clusters(clusters), strict=True):
            track = tracker.update(observation)
            center = centroid(cluster.points)
            update = verdicts.update(
                track.track_id,
                stats.update(track.track_id, index * 100_000_000, center, 1.0),
            )
            if update.verdict is Verdict.RIGID_MOVER:
                graduated_tracks.add(track.track_id)
                buffer.add(
                    track.track_id,
                    Observation(
                        t_ns=index * 100_000_000,
                        keypoints=select_keypoints(cluster.points, config),
                        centroid=center,
                        velocity=Vec3(0.0, 0.0, 0.0),
                        vo_translation=Vec3(0.0, 0.0, 0.0),
                    ),
                )
                track_id_out, source = object_track_id(None, track.track_id)
                snapshot = build_snapshot(
                    index,
                    buffer.observations(track.track_id)[-1],
                    posed[index],
                    track_id_out,
                    source,
                )
                snapshots.append((index, snapshot.centroid))
    print(
        f"KITTI E2E: graduated={sorted(graduated_tracks)} snapshots={len(snapshots)} "
        f"car-proximate keyframes={car_proximate_keyframes}"
    )
    assert car_proximate_keyframes >= 3, "candidate clusters rarely land on labelled cars"
    assert graduated_tracks, "no track graduated to rigid mover on KITTI traffic"
    assert snapshots, "no map-frame snapshots produced"

    # At least one snapshot centroid lands near a labelled car
    # position (same frame, map frame) - the placement claim.
    best = min(
        (centroid_map - to_map_frame(car[1], posed[index])).norm()
        for index, centroid_map in snapshots
        for car in _cars(index)
    )
    print(f"KITTI E2E: nearest snapshot-to-car distance {best:.2f} m")
    assert best <= 4.0, f"nearest snapshot is {best:.2f} m from any labelled car"
