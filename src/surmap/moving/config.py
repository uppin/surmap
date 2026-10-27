"""Moving-object pipeline configuration (design section 4, OQ4).

One config home, next to `surmap.motion`'s existing thresholds.
Values are design starting points, tuned on recorded data (n4).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MovingConfig:
    """Thresholds and caps for stages 1-4."""

    voxel_size_m: float = 0.05
    tau0_m: float = 0.15
    tau_depth_k: float = 0.05  # disparity sigma (px) scaling the Z^2/(f*B) term
    tau_rotation_k: float = 1.0
    focal_px: float = 230.0
    baseline_m: float = 0.11
    min_cluster_points: int = 30
    max_voxels: int = 2_000_000
    eviction_radius_m: float = 40.0
    analysis_hz: float = 5.0
    min_area_ref_px: float = 60.0
    min_area_ref_depth_m: float = 20.0
    max_polygon_vertices: int = 64
    max_areas: int = 32
    max_keypoints: int = 16
