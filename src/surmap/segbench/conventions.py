"""The one place the benchmark's frame and clock are named.

Until the map frame is decided, 3D numbers are Gazebo ENU metres with
the origin at the PX4 home anchor. 2D masks are rectified left-camera
pixels. The clock is simulation time, stored in `t_ns`.

Changing `DEFAULT_SCORING` (or the `scoring` object in a bench file)
changes what a report claims. It does not reproject poses. Every pose
in the bench must already be in `map_frame`, and every `t_ns` must
already be on `clock`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringFrame:
    """Frame, pixel space, and clock a bench report is measured in."""

    map_frame: str = "gazebo_enu"
    pixel_space: str = "rectified"
    clock: str = "sim_time"
    match_radius_m: float = 3.0


DEFAULT_SCORING = ScoringFrame()

MAP_FRAME_NOTE = "Gazebo ENU metres, origin at the PX4 home anchor"
PIXEL_SPACE_NOTE = "Rectified left-camera pixels"
CLOCK_NOTE = "Simulation time in nanoseconds, stored in t_ns"


def is_survivor_label(label: str) -> bool:
    """True when a class or landmark label names a person."""
    text = label.strip().lower()
    return "survivor" in text or "person" in text


def require_scoring(frame: ScoringFrame) -> ScoringFrame:
    """Reject a blank frame, pixel space, or clock, and a negative radius."""
    if not frame.map_frame.strip():
        raise ValueError("scoring map_frame is empty")
    if not frame.pixel_space.strip():
        raise ValueError("scoring pixel_space is empty")
    if not frame.clock.strip():
        raise ValueError("scoring clock is empty")
    if frame.match_radius_m < 0:
        raise ValueError("scoring match_radius_m must be non-negative")
    return frame
