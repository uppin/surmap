"""The SAM surface layer as drawn into the server-rendered cloud view.

A static surface is a translucent splat in its surface colour, so the
RTAB-Map cloud stays readable through it. A moving surface — the smear a
moving object left across the map (`surmap.survey.surfaces`) — is red and
more opaque, drawn over the static ones, so it reads as motion, never as
a shape of the scene. `draw_surface_ids` draws the same pixels as an id
image, so the page can tell which surface is under the cursor.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

# A drawable surface layer: (surface id, map-frame points, moving) per surface.
SurfaceLayer = tuple[tuple[int, NDArray[np.float32], bool], ...]

# Static surface colours, by surface id.
SURFACE_COLOURS = (
    (255, 64, 153),
    (51, 230, 255),
    (255, 217, 26),
    (128, 255, 77),
    (255, 140, 26),
    (179, 102, 255),
    (26, 255, 179),
    (64, 140, 255),
)
SURFACE_ALPHA = 0.5
MOVING_COLOUR = (255, 32, 32)
MOVING_ALPHA = 0.9

Projector = Callable[[NDArray[np.float32]], tuple[NDArray[np.int64], NDArray[np.int64]]]


def _blend(
    colour: tuple[int, int, int], alpha: float, under: NDArray[np.uint8]
) -> NDArray[np.uint8]:
    mixed = alpha * np.asarray(colour, np.float64) + (1.0 - alpha) * under.astype(np.float64)
    return np.round(mixed).astype(np.uint8)


def surface_tint(
    colour: tuple[int, int, int], alpha: float, under: tuple[int, int, int]
) -> tuple[int, int, int]:
    """The pixel `colour` at `alpha` makes over a pixel of colour `under`."""
    r, g, b = (int(value) for value in _blend(colour, alpha, np.array(under, np.uint8)))
    return r, g, b


def _drawn(surfaces: SurfaceLayer) -> SurfaceLayer:
    """Surfaces in drawing order: static first, then moving over them."""
    return tuple(sorted(surfaces, key=lambda surface: surface[2]))


def surface_pixels(
    points: NDArray[np.float32], size: tuple[int, int], project: Projector
) -> NDArray[np.int64]:
    """Flat indices of the pixels a surface's 2x2 splats cover, each once."""
    width, height = size
    u, v = project(points)
    splat = []
    for du, dv in ((0, 0), (1, 0), (0, 1), (1, 1)):
        uu, vv = u + du, v + dv
        on = (uu < width) & (vv < height)
        splat.append(vv[on] * width + uu[on])
    covered: NDArray[np.int64] = np.unique(np.concatenate(splat))
    return covered


def draw_surfaces(
    flat: NDArray[np.uint8], size: tuple[int, int], surfaces: SurfaceLayer, project: Projector
) -> None:
    """Blend every surface into `flat` (an RGBA image as `(width * height, 4)`)."""
    for surface_id, points, moving in _drawn(surfaces):
        if not len(points):
            continue
        # A 2x2 splat makes the (sparse, depth-filtered) surface read over the
        # cloud; each covered pixel is blended once, so alpha means alpha.
        covered = surface_pixels(points, size, project)
        colour = MOVING_COLOUR if moving else SURFACE_COLOURS[surface_id % len(SURFACE_COLOURS)]
        alpha = MOVING_ALPHA if moving else SURFACE_ALPHA
        flat[covered, :3] = _blend(colour, alpha, flat[covered, :3])
        flat[covered, 3] = 255


def draw_surface_ids(
    flat: NDArray[np.uint8], size: tuple[int, int], surfaces: SurfaceLayer, project: Projector
) -> None:
    """Write each surface's id into `flat` on the pixels `draw_surfaces` colours.

    The id is R + 256 * G with alpha 255; a surface drawn later (a moving one)
    owns the pixels it shares, as it does in the colour image.
    """
    for surface_id, points, _ in _drawn(surfaces):
        if not len(points):
            continue
        covered = surface_pixels(points, size, project)
        flat[covered] = (surface_id & 255, (surface_id >> 8) & 255, 0, 255)
