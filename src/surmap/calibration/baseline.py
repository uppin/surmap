"""Rescale a solved stereo estimate to a known baseline.

RTAB-Map's calibration dialog offers the same: when the rig's baseline
is known better than the printed square size, the solved translation
is scaled to it and the scale is reported, with the square size the
solve implied (`square_size_m · scale`) — a scale far from 1 usually
means the square was mis-measured. Intrinsics do not depend on the
square size and are left as solved.
"""

from __future__ import annotations

import dataclasses

from surmap.calibration.port import StereoEstimate


def rescale_baseline(estimate: StereoEstimate, *, expected_baseline_m: float) -> StereoEstimate:
    """`estimate` with its translation scaled to `expected_baseline_m`."""
    if expected_baseline_m <= 0:
        raise ValueError(f"expected baseline must be positive, got {expected_baseline_m}")
    scale = expected_baseline_m / estimate.baseline_m
    tx, ty, tz = estimate.translation_m
    return dataclasses.replace(
        estimate,
        translation_m=(tx * scale, ty * scale, tz * scale),
        baseline_m=expected_baseline_m,
        baseline_scale=estimate.baseline_scale * scale,
    )
