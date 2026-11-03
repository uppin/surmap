"""Frame images for the model: crop, pad, downscale and encode one frame.

Pure Pillow helpers behind `get_frame`. Boxes are pixel `(x0, y0, x1, y1)` in the image they
are applied to; `crop_box_for_object` carries a mask box measured on one image (a run's display
frame) over to another size of the same frame (its full-resolution original).
"""

from __future__ import annotations

from dataclasses import dataclass

from surmap.agent.tools.workspace import BoxXYXY

__all__ = ["EncodedImage", "crop_box_for_object", "frame_image"]


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
    raise NotImplementedError  # TODO(pr-7): implement


def crop_box_for_object(
    box_xyxy: BoxXYXY,
    *,
    measured_on: tuple[int, int],
    image_size: tuple[int, int],
) -> BoxXYXY:
    """A mask box measured on a `measured_on` `(width, height)` image, in `image_size` pixels.

    The two images are the same frame at two resolutions, so each axis scales by its own ratio.
    """
    raise NotImplementedError  # TODO(pr-7): implement
