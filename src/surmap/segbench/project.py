"""Occlusion-aware mask projection.

`surmap.survey.mask_cloud.points_in_mask` keeps every camera point whose
pixel falls inside the polygon. A farther point on the same pixel is
claimed as well, so the mask also takes background behind the subject.
This module keeps the nearest point on each pixel (a z-buffer) and only
then tests the polygon. The original function is unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from surmap.geometry import to_camera_frame, to_map_frame
from surmap.segbench.masks import BoolMask, rasterize_polygon
from surmap.survey.stereo import StereoRig
from surmap.types import Pose, Vec3

# Same near plane as points_in_mask.
MIN_DEPTH_M = 0.05


@dataclass(frozen=True)
class VisiblePoint:
    """The nearest camera point that projects to one pixel."""

    index: int
    u: float
    v: float
    depth_m: float
    camera: Vec3
    mapped: Vec3


def visible_points(
    points: Sequence[Vec3],
    rig: StereoRig,
    width: int,
    height: int,
    pose: Pose | None = None,
    *,
    points_are_map: bool = False,
) -> tuple[VisiblePoint, ...]:
    """One winner per pixel: the smallest depth strictly beyond the near plane.

    Equal depths keep the earlier point. Pixels outside the frame are
    dropped. `mapped` is the map-frame point when `pose` is set, and the
    camera point otherwise.
    """
    if points_are_map:
        if pose is None:
            raise ValueError("map-frame points need a pose before they can be projected")
        camera_pose: Pose | None = pose
    else:
        camera_pose = None
    winners: dict[tuple[int, int], VisiblePoint] = {}
    for index, point in enumerate(points):
        camera = to_camera_frame(point, camera_pose) if camera_pose is not None else point
        if camera.z <= MIN_DEPTH_M:
            continue
        u = rig.fx * camera.x / camera.z + rig.cx
        v = rig.fy * camera.y / camera.z + rig.cy
        if not (0.0 <= u < width and 0.0 <= v < height):
            continue
        pixel = (int(u), int(v))
        if points_are_map:
            mapped = point
        elif pose is not None:
            mapped = to_map_frame(camera, pose)
        else:
            mapped = camera
        candidate = VisiblePoint(index, u, v, camera.z, camera, mapped)
        current = winners.get(pixel)
        if current is None or candidate.depth_m < current.depth_m:
            winners[pixel] = candidate
    return tuple(winners.values())


def project_mask(
    points: Sequence[Vec3],
    rig: StereoRig,
    polygon: Sequence[tuple[float, float]],
    width: int,
    height: int,
    pose: Pose | None = None,
    *,
    points_are_map: bool = False,
) -> tuple[Vec3, ...]:
    """Map-frame (or camera-frame) points the mask claims after the z-buffer.

    The returned point is `VisiblePoint.mapped`. An empty polygon claims
    nothing. Callers of `points_in_mask` are not affected.
    """
    if len(polygon) < 3:
        return ()
    mask = rasterize_polygon(polygon, width, height)
    return masked_visible_points(
        visible_points(
            points,
            rig,
            width,
            height,
            pose,
            points_are_map=points_are_map,
        ),
        mask,
    )


def masked_visible_points(visible: Sequence[VisiblePoint], mask: BoolMask) -> tuple[Vec3, ...]:
    """Winners whose pixel is set in `mask`."""
    kept: list[Vec3] = []
    height, width = mask.shape
    for point in visible:
        column = int(point.u)
        row = int(point.v)
        if row < 0 or column < 0 or row >= height or column >= width:
            continue
        if mask[row, column]:
            kept.append(point.mapped)
    return tuple(kept)
