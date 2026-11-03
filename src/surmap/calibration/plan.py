"""The capture plan: every viewpoint a calibration needs, known up front.

RTAB-Map's readiness bar is stated in image terms — board centre x and
y, size (sqrt of quad area over image area) and skew (the corner angle)
— none of which depends on the intrinsics being solved. So the views
that clear it can be planned before the first frame:

- the board near and centred midway between the two lenses (the
  largest size; centred on one lens, the other eye loses it to the
  stereo disparity);
- far, near each corner of the image (x, y and the smallest size);
- at a middle distance, centred, with each corner of the board in turn
  turned about 45° away (a diagonal tilt changes the corner angle
  RTAB-Map's skew measures; turning one side away barely does).

A view fills a viewpoint when its centre is within one sixth of the
image of the target, its size within 25% of the target size, and the
same board corner is turned away (or none). Distances use a nominal
focal length of one image width (≈53° HFOV): guidance, not measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.port import CornerSet, LensModel

NEAR_SIZE = 0.55
"""Largest board that still leaves its outer squares inside a 4:3 image."""
MID_SIZE = 0.3
"""Small enough that a 45° tilt keeps the near corner in frame."""
CORNER = (0.2, 0.8)
"""Corner targets (normalized): inset so the other eye, shifted by the
stereo disparity, still sees the whole board."""
TILT_DEG = 45.0
_CENTRE_TOLERANCE = 1 / 6
_SIZE_TOLERANCE = 0.25
_DIAGONAL_TILT_DEG = 95.0
"""Mean angle of the far/near corner pair above which the board is tilted."""
_AWAY_RATIO = 0.97
"""The far corner's two edges are under 97% of the near corner's."""


class Tilt(Enum):
    NONE = "none"
    TOP_LEFT_AWAY = "top_left_away"
    TOP_RIGHT_AWAY = "top_right_away"
    BOTTOM_LEFT_AWAY = "bottom_left_away"
    BOTTOM_RIGHT_AWAY = "bottom_right_away"


@dataclass(frozen=True)
class Viewpoint:
    index: int
    target_cell: str
    center_x: float
    center_y: float
    board_size: float
    tilt: Tilt
    tilt_deg: float
    distance_m: float
    instruction: str


def _far_size(lens: LensModel) -> float:
    """Far enough that near − far clears the lens's size bar by 0.02."""
    size_bar = 0.25 if lens is LensModel.FISHEYE else 0.4
    return NEAR_SIZE - size_bar - 0.02


def nominal_distance_m(board: CheckerboardSpec, size: float, width: int, height: int) -> float:
    """Board distance that gives RTAB-Map `size`, at a focal length of one image width."""
    quad_m2 = (board.cols - 1) * board.square_size_m * (board.rows - 1) * board.square_size_m
    return float(width) * math.sqrt(quad_m2 / (size * size * width * height))


_Target = tuple[str, float, float, float, Tilt]
"""(cell, centre x, centre y, size, tilt) of one viewpoint."""


def _targets(lens: LensModel) -> tuple[_Target, ...]:
    far = _far_size(lens)
    lo, hi = CORNER
    corners_away = (
        Tilt.TOP_LEFT_AWAY,
        Tilt.TOP_RIGHT_AWAY,
        Tilt.BOTTOM_LEFT_AWAY,
        Tilt.BOTTOM_RIGHT_AWAY,
    )
    return (
        ("centre", 0.5, 0.5, NEAR_SIZE, Tilt.NONE),
        ("upper_left", lo, lo, far, Tilt.NONE),
        ("upper_right", hi, lo, far, Tilt.NONE),
        ("lower_left", lo, hi, far, Tilt.NONE),
        ("lower_right", hi, hi, far, Tilt.NONE),
        *(("centre", 0.5, 0.5, MID_SIZE, tilt) for tilt in corners_away),
    )


def _instruction(target: _Target, distance: float, *, near: bool) -> str:
    cell, _, _, _, tilt = target
    if near:
        return (
            f"Hold the board facing the camera, about {distance:.2f} m away and "
            "centred midway between the two lenses, so both images show all of it."
        )
    if tilt is Tilt.NONE:
        return (
            f"Hold the board facing the camera, about {distance:.1f} m away, "
            f"its centre at the {cell.replace('_', ' ')} of the image."
        )
    corner = tilt.value.removesuffix("_away").replace("_", "-")
    return (
        f"Hold the board about {distance:.1f} m away at the centre of the image, "
        f"and tilt it about {TILT_DEG:.0f}° so its {corner} corner is farther from the camera."
    )


def capture_plan(
    board: CheckerboardSpec, *, width: int, height: int, lens: LensModel
) -> tuple[Viewpoint, ...]:
    """The viewpoints that, filled, clear RTAB-Map's readiness bar."""
    plan = []
    for index, target in enumerate(_targets(lens)):
        cell, x, y, size, tilt = target
        distance = nominal_distance_m(board, size, width, height)
        plan.append(
            Viewpoint(
                index=index,
                target_cell=cell,
                center_x=x,
                center_y=y,
                board_size=size,
                tilt=tilt,
                tilt_deg=0.0 if tilt is Tilt.NONE else TILT_DEG,
                distance_m=round(distance, 2),
                instruction=_instruction(target, distance, near=index == 0),
            )
        )
    return tuple(plan)


def _angle_deg(at: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    ux, uy = a[0] - at[0], a[1] - at[1]
    vx, vy = b[0] - at[0], b[1] - at[1]
    cos = (ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def tilt_of(corners: CornerSet, board: CheckerboardSpec) -> Tilt:
    """Which board corner is turned away, read from the image.

    Tilting the board about a diagonal leaves that diagonal's corners at
    one depth and widens the angles at the other two, the far and the
    near corner; perspective then draws the far one with shorter edges.
    So: the opposite pair with the widest mean angle (> 95°) is far and
    near, the one whose two edges are shorter (< 97% of the other's) is
    far, and its place around the quad's centre names it. Image
    positions, not detection order, so a board detected from its far
    end reads the same; a parallelogram (no perspective) reads as none.
    """
    quad = (corners[0], corners[board.cols - 1], corners[-1], corners[-board.cols])
    angles = [_angle_deg(quad[i], quad[i - 1], quad[(i + 1) % 4]) for i in range(4)]
    reach = [
        math.dist(quad[i], quad[i - 1]) + math.dist(quad[i], quad[(i + 1) % 4]) for i in range(4)
    ]
    pair = max(((0, 2), (1, 3)), key=lambda p: angles[p[0]] + angles[p[1]])
    if (angles[pair[0]] + angles[pair[1]]) / 2 <= _DIAGONAL_TILT_DEG:
        return Tilt.NONE
    far, near = sorted(pair, key=lambda i: reach[i])
    if reach[far] >= _AWAY_RATIO * reach[near]:
        return Tilt.NONE
    cx = sum(p[0] for p in quad) / 4
    cy = sum(p[1] for p in quad) / 4
    top, left = quad[far][1] < cy, quad[far][0] < cx
    return {
        (True, True): Tilt.TOP_LEFT_AWAY,
        (True, False): Tilt.TOP_RIGHT_AWAY,
        (False, True): Tilt.BOTTOM_LEFT_AWAY,
        (False, False): Tilt.BOTTOM_RIGHT_AWAY,
    }[(top, left)]


def fills(viewpoint: Viewpoint, *, x: float, y: float, size: float, tilt: Tilt) -> bool:
    """Whether a view at (x, y, size, tilt) fills `viewpoint`."""
    return (
        abs(x - viewpoint.center_x) <= _CENTRE_TOLERANCE
        and abs(y - viewpoint.center_y) <= _CENTRE_TOLERANCE
        and abs(size / viewpoint.board_size - 1) <= _SIZE_TOLERANCE
        and tilt is viewpoint.tilt
    )
