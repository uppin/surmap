"""Project a SAM mask polygon onto a camera-frame cloud.

`points_in_mask` keeps the points whose image projection lies inside
the polygon and inside the frame, dropping anything at or nearer than
5 cm. When a pose is passed, the survivors are transformed into the
map frame with `surmap.geometry.to_map_frame`. The returned points are
a registration layer: nothing here is written back into RTAB-Map.
"""

from __future__ import annotations

from surmap.geometry import to_map_frame
from surmap.survey.stereo import StereoRig
from surmap.types import Pose, Vec3

# Same near-plane gate as the on-board box lift and the demo overlay.
_MIN_DEPTH_M = 0.05


def points_in_mask(
    points: tuple[Vec3, ...],
    rig: StereoRig,
    polygon: tuple[tuple[float, float], ...],
    width: int,
    height: int,
    pose: Pose | None = None,
) -> tuple[Vec3, ...]:
    """Camera-frame points the mask claims, in the map frame when `pose` is set.

    `polygon` is in frame pixels, the same space as `width` and `height`.
    A projection outside `[0, width) × [0, height)` is not a mask pixel.
    An empty polygon claims nothing.
    """
    if len(polygon) < 3:
        return ()
    kept: list[Vec3] = []
    for point in points:
        if point.z <= _MIN_DEPTH_M:
            continue
        u = rig.fx * point.x / point.z + rig.cx
        v = rig.fy * point.y / point.z + rig.cy
        if not (0.0 <= u < width and 0.0 <= v < height):
            continue
        if not _projection_inside_polygon(u, v, polygon):
            continue
        kept.append(point if pose is None else to_map_frame(point, pose))
    return tuple(kept)


def _projection_inside_polygon(
    u: float, v: float, polygon: tuple[tuple[float, float], ...]
) -> bool:
    """Even-odd test. The ring closes from the last vertex back to the first."""
    inside = False
    previous_x, previous_y = polygon[-1]
    for x, y in polygon:
        straddles = (y > v) != (previous_y > v)
        if straddles and u < (previous_x - x) * (v - y) / (previous_y - y) + x:
            inside = not inside
        previous_x, previous_y = x, y
    return inside
