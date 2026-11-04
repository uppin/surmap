"""Where RTAB-Map's tracked keypoints sit in the raw left frame: its odometry reports them in
rectified pixels, a viewer draws them over the camera image it was given."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from surmap.slam.stream_protocol import Rectification


def rectified_to_raw(
    pixels: NDArray[np.float64], rectification: Rectification
) -> NDArray[np.float64]:
    """Rectified left-camera pixels to raw (distorted) display pixels.

    Undoes the rectification rotation (raw ray = R1ᵀ · rectified ray), then
    applies the raw camera's radial-tangential distortion.
    """
    fx, fy, cx, cy = rectification.rectified
    rays = np.stack(
        [(pixels[:, 0] - cx) / fx, (pixels[:, 1] - cy) / fy, np.ones(len(pixels))], axis=1
    )
    # Row vectors: R1ᵀ · r is r @ R1.
    raw_rays = rays @ np.array(rectification.rotation, dtype=np.float64).reshape(3, 3)
    x = raw_rays[:, 0] / raw_rays[:, 2]
    y = raw_rays[:, 1] / raw_rays[:, 2]
    k1, k2, p1, p2 = rectification.distortion
    r2 = x * x + y * y
    radial = 1 + k1 * r2 + k2 * r2 * r2
    xd = x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
    yd = y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
    raw_fx, raw_fy, raw_cx, raw_cy = rectification.raw
    return np.stack([raw_fx * xd + raw_cx, raw_fy * yd + raw_cy], axis=1)
