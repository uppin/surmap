"""Builders for checkerboard detections (9x6 inner corners, row-major)."""

from surmap.calibration.port import CornerSet

COLS, ROWS = 9, 6


def a_detection(
    cx: float,
    cy: float,
    *,
    width_px: float = 160.0,
    shear: float = 0.0,
    away: str | None = None,
) -> CornerSet:
    """A 9x6 detection centred at (cx, cy), `width_px` across.

    `shear` slants the grid like a tilted board: skew (RTAB-Map's
    measure) is 2·|atan(shear)|, so 0.35 reads as about 0.67.
    `away` ("top_left", "top_right", "bottom_left", "bottom_right")
    turns that corner of the board away from the camera: the grid near
    it is drawn up to 30% smaller, as perspective draws it.
    """
    pitch = width_px / (COLS - 1)

    def shrink(c: int, r: int) -> float:
        """Scale towards the centre at grid cell (c, r)."""
        if away is None:
            return 1.0
        vertical, horizontal = away.split("_")
        u = c / (COLS - 1) if horizontal == "right" else 1 - c / (COLS - 1)
        v = r / (ROWS - 1) if vertical == "bottom" else 1 - r / (ROWS - 1)
        return 1 - 0.3 * u * v

    return tuple(
        (
            cx + (c - (COLS - 1) / 2) * pitch * shrink(c, r) + shear * (r - (ROWS - 1) / 2) * pitch,
            cy + (r - (ROWS - 1) / 2) * pitch * shrink(c, r),
        )
        for r in range(ROWS)
        for c in range(COLS)
    )


def shifted(corners: CornerSet, dx: float) -> CornerSet:
    """The same detection `dx` pixels to the side (the other eye)."""
    return tuple((u + dx, v) for u, v in corners)


DIVERSE_VIEWS: tuple[CornerSet, ...] = (
    a_detection(100, 80, width_px=80),
    a_detection(540, 400, width_px=80, shear=0.35),
    a_detection(320, 240, width_px=420),
    a_detection(320, 240, width_px=420, shear=0.35),
)
"""Left-eye views spanning position, size and tilt as RTAB-Map requires."""


def width_for(board_size: float, width: int = 640, height: int = 480) -> float:
    """Grid width (px) whose 8:5 inner quad has RTAB-Map size `board_size`."""
    return float(board_size * ((width * height) / ((ROWS - 1) / (COLS - 1))) ** 0.5)
