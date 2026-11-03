"""Calibration session: per-view feedback, coverage, next-pose guidance.

Pure domain logic — corners in, feedback out. Each view is measured
the way RTAB-Map's calibration dialog does it (`getParams` in
`guilib/src/CalibrationDialog.cpp`): board centre x and y over the
image, size = sqrt(board quad area / image area), and skew = 2·|90° −
the angle at the board's upper-right corner|, all in [0, 1]. A view
is kept unless an earlier one matches it on all four (|Δx|, |Δy| <
0.1, |Δsize| < 0.05, |Δskew| < 0.1). The session is ready when enough
views are kept and their spreads (max − min) reach RTAB-Map's bar:
x, y > 0.5, size > 0.4 (0.25 for a fisheye lens, as RTAB-Map
relaxes it), skew > 0.5. Without the skew spread a planar
target cannot fix the focal length, so flat views are never enough.

Guidance follows the capture plan (`surmap.calibration.plan`): every
viewpoint the bar needs is known once the image size is, each kept
view is matched to the viewpoint it fills, and the suggestion is the
remaining viewpoint that widens what is still missing — position
first, then tilt, then distance — with the camera move from the
current view. A view that fills a remaining viewpoint is kept even when
the duplicate rule would call it alike: opposite tilts read the same
unsigned skew but constrain the solve differently. Once the plan is
used up and the bar is still not met, guidance falls back to the first
uncovered cell of a 3x3 grid, then tilt, then distance. Distances use
a nominal focal length of one image width (≈53° HFOV); they are
guidance, not measurement.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.plan import (
    Tilt,
    Viewpoint,
    capture_plan,
    fills,
    nominal_distance_m,
    tilt_of,
)
from surmap.calibration.port import CalibrationView, CornerSet, LensModel

_CELLS: tuple[tuple[str, float, float], ...] = (
    ("centre", 0.5, 0.5),
    ("upper_left", 1 / 6, 1 / 6),
    ("upper_right", 5 / 6, 1 / 6),
    ("lower_left", 1 / 6, 5 / 6),
    ("lower_right", 5 / 6, 5 / 6),
    ("upper_centre", 0.5, 1 / 6),
    ("lower_centre", 0.5, 5 / 6),
    ("centre_left", 1 / 6, 0.5),
    ("centre_right", 5 / 6, 0.5),
)

# RTAB-Map's duplicate thresholds (x, y, size, skew) and readiness bar.
_SIMILAR = (0.1, 0.1, 0.05, 0.1)
_READY_SPREAD = (0.5, 0.5, 0.4, 0.5)
_FISHEYE_READY_SPREAD = (0.5, 0.5, 0.25, 0.5)


class ViewStatus(Enum):
    ACCEPTED = "accepted"
    BOARD_NOT_FOUND = "board_not_found"
    TOO_SIMILAR = "too_similar"
    FRAME_UNREADABLE = "frame_unreadable"
    NO_VIEW = "no_view"
    """Progress report not tied to a frame (e.g. an early finish)."""


@dataclass(frozen=True)
class ViewGeometry:
    """One board detection in RTAB-Map's terms, each in [0, 1]."""

    x: float
    y: float
    size: float
    skew: float
    fraction: float
    """Bounding-box area over image area (drives the distance guess)."""

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.size, self.skew)


def measure(corners: CornerSet, board: CheckerboardSpec, width: int, height: int) -> ViewGeometry:
    """RTAB-Map's `getParams` for a full row-major detection."""
    up_left, up_right = corners[0], corners[board.cols - 1]
    down_left, down_right = corners[-board.cols], corners[-1]
    # Convex quad area from its diagonals: |p × q| / 2.
    px, py = down_right[0] - up_left[0], down_right[1] - up_left[1]
    qx, qy = up_right[0] - down_left[0], up_right[1] - down_left[1]
    area = abs(px * qy - py * qx) / 2
    abx, aby = up_left[0] - up_right[0], up_left[1] - up_right[1]
    cbx, cby = down_right[0] - up_right[0], down_right[1] - up_right[1]
    cos_angle = (abx * cbx + aby * cby) / (math.hypot(abx, aby) * math.hypot(cbx, cby))
    angle = math.acos(max(-1.0, min(1.0, cos_angle)))
    us = [p[0] for p in corners]
    vs = [p[1] for p in corners]
    return ViewGeometry(
        x=sum(us) / len(us) / width,
        y=sum(vs) / len(vs) / height,
        size=min(1.0, math.sqrt(area / (width * height))),
        skew=min(1.0, 2 * abs(math.pi / 2 - angle)),
        fraction=(max(us) - min(us)) * (max(vs) - min(vs)) / (width * height),
    )


def _same_orientation(left: CornerSet, right: CornerSet) -> bool:
    """Both eyes list corners from the same board end (first→last agree)."""
    lx, ly = left[-1][0] - left[0][0], left[-1][1] - left[0][1]
    rx, ry = right[-1][0] - right[0][0], right[-1][1] - right[0][1]
    return lx * rx + ly * ry >= 0


@dataclass(frozen=True)
class MoveSuggestion:
    target_cell: str
    move_x_m: float
    move_y_m: float
    move_z_m: float
    target_distance_m: float
    instruction: str
    viewpoint_index: int = -1
    """The capture-plan viewpoint this suggests, or -1."""


def _hold(cell: str, instruction: str) -> MoveSuggestion:
    """A suggestion with no camera move: change the board, not the position."""
    return MoveSuggestion(cell, 0.0, 0.0, 0.0, 0.0, instruction)


_DONE = _hold(
    "done", "Enough diverse views collected — finish the stream to solve the calibration."
)
_TILT_MORE = _hold(
    "tilt",
    "Tilt the board about 45° so one corner is farther from the camera, and hold "
    "still; then turn a different corner away.",
)
_COME_NEARER = _hold("near", "Bring the board closer, until it fills most of the image.")
_MOVE_FARTHER = _hold(
    "far", "Move the board farther away, until it covers about a tenth of the image."
)


@dataclass(frozen=True)
class ViewFeedback:
    frame_id: int
    status: ViewStatus
    left_found: bool
    right_found: bool
    corners_left: int
    corners_right: int
    board_center_x: float
    board_center_y: float
    board_fraction: float
    board_size: float
    board_skew: float
    accepted_views: int
    required_views: int
    coverage_fraction: float
    x_spread: float
    y_spread: float
    size_spread: float
    skew_spread: float
    ready: bool
    suggestion: MoveSuggestion
    message: str = ""
    matched_viewpoint: int = -1
    """The capture-plan viewpoint this view filled, or -1."""
    remaining_viewpoints: tuple[int, ...] = ()


@dataclass(frozen=True)
class _Observation:
    left_found: bool = False
    right_found: bool = False
    corners_left: int = 0
    corners_right: int = 0
    geometry: ViewGeometry | None = None
    matched_viewpoint: int = -1


_MESSAGES = {
    ViewStatus.ACCEPTED: "View accepted.",
    ViewStatus.BOARD_NOT_FOUND: "Checkerboard not found in both eyes.",
    ViewStatus.TOO_SIMILAR: "View too similar to an accepted view — move or tilt the board.",
    ViewStatus.FRAME_UNREADABLE: "Frame could not be decoded.",
    ViewStatus.NO_VIEW: "",
}


@dataclass
class CalibrationSession:
    board: CheckerboardSpec
    width: int
    height: int
    min_views: int = 8
    lens: LensModel = LensModel.PINHOLE_RADTAN
    _views: list[CalibrationView] = field(default_factory=list)
    _geometry: list[ViewGeometry] = field(default_factory=list)
    _cells: list[str] = field(default_factory=list)
    _plan: tuple[Viewpoint, ...] = ()
    _remaining: list[int] = field(default_factory=list)

    @property
    def views(self) -> tuple[CalibrationView, ...]:
        return tuple(self._views)

    def _ensure_plan(self) -> tuple[Viewpoint, ...]:
        """Build the plan, and what remains of it, once the size is known."""
        if not self._plan and self.width > 0 and self.height > 0:
            self._plan = capture_plan(
                self.board, width=self.width, height=self.height, lens=self.lens
            )
            self._remaining = [v.index for v in self._plan]
        return self._plan

    @property
    def plan(self) -> tuple[Viewpoint, ...]:
        """The capture plan; empty until the image size is known."""
        return self._ensure_plan()

    @property
    def remaining_viewpoints(self) -> tuple[int, ...]:
        self._ensure_plan()
        return tuple(self._remaining)

    def spreads(self) -> tuple[float, float, float, float]:
        """Max − min of x, y, size and skew over accepted views."""
        if not self._geometry:
            return (0.0, 0.0, 0.0, 0.0)
        columns = zip(*(g.as_tuple() for g in self._geometry), strict=True)
        x, y, size, skew = (max(c) - min(c) for c in columns)
        return (x, y, size, skew)

    def _spread_ok(self) -> tuple[bool, bool, bool, bool]:
        bars = _FISHEYE_READY_SPREAD if self.lens is LensModel.FISHEYE else _READY_SPREAD
        x, y, size, skew = (s > bar for s, bar in zip(self.spreads(), bars, strict=True))
        return (x, y, size, skew)

    @property
    def ready(self) -> bool:
        return len(self._views) >= self.min_views and all(self._spread_ok())

    def observe(
        self,
        *,
        frame_id: int,
        left: CornerSet | None,
        right: CornerSet | None,
    ) -> ViewFeedback:
        expected = self.board.corner_count
        seen = _Observation(
            left_found=left is not None,
            right_found=right is not None,
            corners_left=len(left) if left else 0,
            corners_right=len(right) if right else 0,
        )
        if left is None or right is None or len(left) != expected or len(right) != expected:
            return self._feedback(frame_id, ViewStatus.BOARD_NOT_FOUND, seen)
        if not _same_orientation(left, right):
            right = tuple(reversed(right))
        geometry = measure(left, self.board, self.width, self.height)
        filled = self._filled_viewpoint(geometry, tilt_of(left, self.board))
        seen = _Observation(True, True, len(left), len(right), geometry, filled)
        if filled >= 0:
            self._remaining.remove(filled)
        elif any(self._similar(geometry, kept) for kept in self._geometry):
            return self._feedback(frame_id, ViewStatus.TOO_SIMILAR, seen)
        self._views.append(CalibrationView(left=left, right=right))
        self._geometry.append(geometry)
        self._cells.append(self._cell_of(geometry.x, geometry.y))
        return self._feedback(frame_id, ViewStatus.ACCEPTED, seen)

    def unreadable(self, *, frame_id: int, reason: str) -> ViewFeedback:
        """Feedback for a frame whose bytes could not be decoded."""
        return self._feedback(
            frame_id, ViewStatus.FRAME_UNREADABLE, _Observation(), f"Frame unreadable: {reason}"
        )

    def progress(self, message: str) -> ViewFeedback:
        """Current progress, not tied to a frame."""
        return self._feedback(0, ViewStatus.NO_VIEW, _Observation(), message)

    def _filled_viewpoint(self, geometry: ViewGeometry, tilt: Tilt) -> int:
        for index in self.remaining_viewpoints:
            viewpoint = self.plan[index]
            if fills(viewpoint, x=geometry.x, y=geometry.y, size=geometry.size, tilt=tilt):
                return index
        return -1

    def _next_viewpoint(self) -> Viewpoint | None:
        """The remaining viewpoint that widens the first spread still short."""
        remaining = [self.plan[i] for i in self.remaining_viewpoints]
        if not remaining:
            return None
        x_ok, y_ok, size_ok, skew_ok = self._spread_ok()
        columns: list[tuple[float, ...]] = list(
            zip(*(g.as_tuple() for g in self._geometry), strict=True)
        )

        def widens(value: float, column: int) -> bool:
            if not columns:
                return True
            return value < min(columns[column]) or value > max(columns[column])

        wanted: list[Callable[[Viewpoint], bool]] = []
        if not (x_ok and y_ok):
            wanted.append(lambda v: widens(v.center_x, 0) or widens(v.center_y, 1))
        if not skew_ok:
            wanted.append(lambda v: v.tilt is not Tilt.NONE)
        if not size_ok:
            wanted.append(lambda v: widens(v.board_size, 2))
        for wants in wanted:
            for viewpoint in remaining:
                if wants(viewpoint):
                    return viewpoint
        return remaining[0]

    def _suggest_viewpoint(
        self, viewpoint: Viewpoint, current: ViewGeometry | None
    ) -> MoveSuggestion:
        if current is None:
            return MoveSuggestion(
                viewpoint.target_cell,
                0.0,
                0.0,
                0.0,
                viewpoint.distance_m,
                viewpoint.instruction,
                viewpoint.index,
            )
        # Camera frame (x right, y down, z forward), from the current view.
        distance = nominal_distance_m(self.board, current.size, self.width, self.height)
        # Nominal focal of one image width: a normalized offset dx is dx·d metres.
        move_x = -(viewpoint.center_x - current.x) * distance
        move_y = -(viewpoint.center_y - current.y) * self.height * distance / self.width
        return MoveSuggestion(
            viewpoint.target_cell,
            round(move_x, 3),
            round(move_y, 3),
            round(distance - viewpoint.distance_m, 3),
            viewpoint.distance_m,
            viewpoint.instruction,
            viewpoint.index,
        )

    @staticmethod
    def _similar(a: ViewGeometry, b: ViewGeometry) -> bool:
        return all(
            abs(p - q) < limit
            for p, q, limit in zip(a.as_tuple(), b.as_tuple(), _SIMILAR, strict=True)
        )

    @staticmethod
    def _cell_of(cx: float, cy: float) -> str:
        col = min(2, int(cx * 3))
        row = min(2, int(cy * 3))
        for name, tx, ty in _CELLS:
            if (min(2, int(tx * 3)), min(2, int(ty * 3))) == (col, row):
                return name
        return "centre"

    def _suggest(self, current: ViewGeometry | None) -> MoveSuggestion:
        if self.ready:
            return _DONE
        planned = self._next_viewpoint()
        if planned is not None:
            return self._suggest_viewpoint(planned, current)
        return self._fallback_suggestion(current)

    def _fallback_suggestion(self, current: ViewGeometry | None) -> MoveSuggestion:
        """Past the plan and still short of the bar: ask for what is missing."""
        x_ok, y_ok, size_ok, skew_ok = self._spread_ok()
        covered = set(self._cells)
        uncovered = [c for c in _CELLS if c[0] not in covered]
        if (not x_ok or not y_ok) and uncovered:
            return self._suggest_cell(uncovered[0], current)
        if not skew_ok:
            return _TILT_MORE
        if not size_ok:
            nearest = max(g.size for g in self._geometry)
            return _COME_NEARER if nearest < 0.5 else _MOVE_FARTHER
        return self._suggest_cell(uncovered[0] if uncovered else _CELLS[0], current)

    def _suggest_cell(
        self, cell: tuple[str, float, float], current: ViewGeometry | None
    ) -> MoveSuggestion:
        name, tx, ty = cell
        place = "centre" if name == "centre" else name.replace("_", " ")
        if current is None:
            return MoveSuggestion(
                name,
                0.0,
                0.0,
                0.0,
                0.0,
                f"Place the checkerboard so its centre is at the {place} of the image, "
                "facing the camera, and hold still.",
            )
        # Nominal focal (one image width) turns pixel offsets into a
        # camera move at the board's estimated distance.
        fx_nominal = float(self.width)
        area_m2 = self.board.board_width_m * self.board.board_height_m
        distance = fx_nominal * math.sqrt(
            area_m2 / max(1e-6, current.fraction * self.width * self.height)
        )
        move_x = -(tx - current.x) * self.width * distance / fx_nominal
        move_y = -(ty - current.y) * self.height * distance / fx_nominal
        return MoveSuggestion(
            name,
            round(move_x, 3),
            round(move_y, 3),
            0.0,
            round(distance, 2),
            f"Move the camera so the checkerboard centre reaches the {place} of the "
            f"image (about {distance:.1f} m from the board); tilt the board slightly.",
        )

    def _feedback(
        self, frame_id: int, status: ViewStatus, seen: _Observation, message: str = ""
    ) -> ViewFeedback:
        g = seen.geometry
        x_spread, y_spread, size_spread, skew_spread = self.spreads()
        return ViewFeedback(
            frame_id=frame_id,
            status=status,
            left_found=seen.left_found,
            right_found=seen.right_found,
            corners_left=seen.corners_left,
            corners_right=seen.corners_right,
            board_center_x=g.x if g else 0.0,
            board_center_y=g.y if g else 0.0,
            board_fraction=g.fraction if g else 0.0,
            board_size=g.size if g else 0.0,
            board_skew=g.skew if g else 0.0,
            accepted_views=len(self._views),
            required_views=self.min_views,
            coverage_fraction=len(set(self._cells)) / len(_CELLS),
            x_spread=x_spread,
            y_spread=y_spread,
            size_spread=size_spread,
            skew_spread=skew_spread,
            ready=self.ready,
            suggestion=self._suggest(g),
            message=message or _MESSAGES[status],
            matched_viewpoint=seen.matched_viewpoint,
            remaining_viewpoints=self.remaining_viewpoints,
        )
