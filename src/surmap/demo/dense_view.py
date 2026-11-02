"""A frame's dense depth as an image the page lays over the video.

The page's "Dense depth" toggle asks the server for the shown frame's
depth (`GET /runs/<run_id>/dense-depth`): RTAB-Map's own dense stereo,
the SGBM disparity its sidecar journalled for that frame, read per
display pixel (`surmap.slam.dense.display_depth`) and painted in the
same near → far ramp as the tracked points. Pixels with no match stay
transparent, so the frame shows through. It is a read-only view of
RTAB-Map's output (docs/architecture.md section 1).
"""

from __future__ import annotations

import io

import numpy as np
from numpy.typing import NDArray
from PIL import Image


def dense_depth_png(
    depth_m: NDArray[np.float32],
    size: tuple[int, int],
    stops: tuple[float, float, float],
    colours: tuple[tuple[int, int, int], ...],
) -> bytes:
    """Depth (0 = no match) as an RGBA PNG of `size`, coloured as the overlay's points are."""
    ramp = np.array(colours, np.float64)
    rgba = np.zeros((*depth_m.shape, 4), np.uint8)
    for channel in range(3):
        # Linear between the stops and clamped past them, as `depth_colour` blends.
        rgba[..., channel] = np.round(np.interp(depth_m, stops, ramp[:, channel]))
    rgba[..., 3] = np.where(depth_m > 0, 255, 0)
    image = Image.fromarray(rgba, "RGBA")
    if image.size != size:
        image = image.resize(size, Image.Resampling.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
