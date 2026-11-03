"""Frame images for the model: crop, pad, downscale and encode one frame.

Pure Pillow helpers behind `get_frame`. Boxes are pixel `(x0, y0, x1, y1)` in the image they
are applied to; `crop_box_for_object` carries a mask box measured on one image (a run's display
frame) over to another size of the same frame (its full-resolution original).
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

from PIL import Image

from surmap.agent.tools.port import BoxXYXY

__all__ = ["EncodedImage", "crop_box_for_object", "frame_image"]

_JPEG_QUALITY = 85


@dataclass(frozen=True)
class EncodedImage:
    """An encoded image and its pixel size."""

    data: bytes
    media_type: str
    width: int
    height: int


def frame_image(
    image: bytes,
    *,
    crop: BoxXYXY | None = None,
    pad_px: int = 0,
    max_side: int | None = None,
) -> EncodedImage:
    """`image` (any Pillow-readable encoding) cropped, downscaled and encoded as JPEG.

    `crop`, grown by `pad_px` on every side and clamped to the image, selects the region; the
    whole image without it. `max_side` then downscales, keeping the aspect ratio, so the longer
    side is at most that many pixels; an image already within it is not enlarged. Raises
    `ValueError` for a crop with no area inside the image or a `max_side` below 1.
    """
    if max_side is not None and max_side < 1:
        raise ValueError("max_side must be at least 1 pixel")
    with Image.open(io.BytesIO(image)) as opened:
        rgb = opened.convert("RGB")
    if crop is not None:
        rgb = rgb.crop(_padded_box(crop, pad_px, rgb.size))
    if max_side is not None and max(rgb.size) > max_side:
        scale = max_side / max(rgb.size)
        size = (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale)))
        rgb = rgb.resize(size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return EncodedImage(buffer.getvalue(), "image/jpeg", rgb.width, rgb.height)


def crop_box_for_object(
    box_xyxy: BoxXYXY,
    *,
    measured_on: tuple[int, int],
    image_size: tuple[int, int],
) -> BoxXYXY:
    """A mask box measured on a `measured_on` `(width, height)` image, in `image_size` pixels.

    The two images are the same frame at two resolutions, so each axis scales by its own ratio.
    """
    x_scale = image_size[0] / measured_on[0]
    y_scale = image_size[1] / measured_on[1]
    x0, y0, x1, y1 = box_xyxy
    return (x0 * x_scale, y0 * y_scale, x1 * x_scale, y1 * y_scale)


def _padded_box(box: BoxXYXY, pad_px: int, size: tuple[int, int]) -> tuple[int, int, int, int]:
    """`box` grown by `pad_px` and clamped to an image of `size`, as whole pixels."""
    width, height = size
    x0, y0, x1, y1 = box
    left = max(0, math.floor(min(x0, x1) - pad_px))
    top = max(0, math.floor(min(y0, y1) - pad_px))
    right = min(width, math.ceil(max(x0, x1) + pad_px))
    bottom = min(height, math.ceil(max(y0, y1) + pad_px))
    if right <= left or bottom <= top:
        raise ValueError(f"crop {box} has no area inside the {width} x {height} image")
    return (left, top, right, bottom)
