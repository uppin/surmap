"""A frame's dense depth as an image the page lays over the video.

The page's "Dense depth" toggle asks the server for the shown frame's
depth (`GET /dense-depth`): the stereo reconstructor's per-pixel depth
for that frame's display pair (`StereoReconstructor.depth_map`),
painted in the same near → far ramp as the tracked points, stretched
to the frame's display size. Pixels with no stereo match stay
transparent, so the frame shows through. It is a view of the pair
only: nothing here reaches RTAB-Map (docs/architecture.md section 1).
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
