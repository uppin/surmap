"""Checkerboard target geometry (domain, no vision dependency)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckerboardSpec:
    """Inner-corner grid (cols x rows) and the square size in metres."""

    cols: int
    rows: int
    square_size_m: float

    def __post_init__(self) -> None:
        if self.cols < 2 or self.rows < 2:
            raise ValueError("checkerboard needs at least 2x2 inner corners")
        if self.square_size_m <= 0:
            raise ValueError("checkerboard square_size_m must be positive")

    @property
    def corner_count(self) -> int:
        return self.cols * self.rows

    @property
    def board_width_m(self) -> float:
        """Physical width including the outer half-squares."""
        return (self.cols + 1) * self.square_size_m

    @property
    def board_height_m(self) -> float:
        return (self.rows + 1) * self.square_size_m

    def object_points(self) -> tuple[tuple[float, float, float], ...]:
        """Inner corners on the board plane (Z=0), row-major, metres."""
        return tuple(
            (c * self.square_size_m, r * self.square_size_m, 0.0)
            for r in range(self.rows)
            for c in range(self.cols)
        )
