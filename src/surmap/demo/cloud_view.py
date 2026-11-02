"""The 3D pane: its server-side render and the console session's view of it.

`render_cloud_view` draws every map point from a `CloudPose` (an orbit
camera), nearest point per pixel, with the SAM surface layer over it.

`CloudViewer` is the pane's state for the whole console session, not for
one run: the PTZ pose, whether surfaces are shown, a version that bumps
on every change, and the last scene it drew. Every run's
`PlaybackControls` uses the server's one viewer, so a pose set during a
run (or with nothing playing) is the pose of the next. A PTZ action
answers with `rerender()`: the last scene drawn again from the new pose,
so the pane moves after a run has finished or on a scrubbed moment, not
only with the next map update. `render_view` adds the scene's id image
(`render_cloud_ids`): which surface each pixel shows, for hover picking.
"""

from __future__ import annotations

import base64
import io
import math
import threading
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.surface_render import SurfaceLayer, draw_surface_ids, draw_surfaces

Bounds = tuple[NDArray[np.float32], NDArray[np.float32]]

CLOUD_VIEW_PX = (880, 440)


def png_base64(rgba: NDArray[np.uint8]) -> str:
    """An (H, W, 4) RGBA array as a base64 PNG (the panes' shared encoding)."""
    out = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


@dataclass(frozen=True)
class CloudPose:
    """The 3D pane's PTZ pose: orbit angles, zoom and ground-plane pan.

    The floor plan is this same pose family fixed at top-down; the
    cloud view is the one the viewer orbits.
    """

    azimuth: float = -0.8
    elevation: float = 0.85
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_z: float = 0.0


def _project_points(
    points: NDArray[np.float32],
    pose: CloudPose,
    centre: NDArray[np.float64],
    span: float,
    size: tuple[int, int],
) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64], NDArray[np.int64]]:
    """Map-frame points to (u, v, depth, point indices) under the orbit pose."""
    width, height = size
    rel = points.astype(np.float64) - centre
    x, up, fwd = rel[:, 0], -rel[:, 1], rel[:, 2]
    ca, sa = math.cos(pose.azimuth), math.sin(pose.azimuth)
    x, fwd = x * ca - fwd * sa, x * sa + fwd * ca
    ce, se = math.cos(pose.elevation), math.sin(pose.elevation)
    up, fwd = up * ce - fwd * se, up * se + fwd * ce
    distance = span * 1.9 * pose.zoom
    depth = distance - fwd
    focal = 1.0 / math.tan(0.35)
    inside = depth > distance * 0.05
    indices = np.flatnonzero(inside)
    u = np.floor(width / 2 + focal * x[inside] / depth[inside] * (height / 2))
    v = np.floor(height / 2 - focal * up[inside] / depth[inside] * (height / 2))
    ui, vi = u.astype(np.int64), v.astype(np.int64)
    on = (ui >= 0) & (ui < width) & (vi >= 0) & (vi < height)
    return ui[on], vi[on], depth[inside][on], indices[on]


def _framing(bounds: Bounds, pose: CloudPose) -> tuple[NDArray[np.float64], float]:
    """The orbit centre (panned) and span a view of `bounds` is drawn with."""
    lo, hi = (np.asarray(bound, dtype=np.float64) for bound in bounds)
    centre = (lo + hi) / 2.0
    centre[0] += pose.pan_x
    centre[2] += pose.pan_z
    return centre, max(float(np.max(hi - lo)), 0.5)


def render_cloud_ids(
    pose: CloudPose,
    bounds: Bounds,
    size: tuple[int, int] = CLOUD_VIEW_PX,
    surfaces: SurfaceLayer = (),
) -> str:
    """The id image of `render_cloud_view`'s surface layer, as base64 PNG.

    Same size and projection; each surface pixel holds its id as R + 256 * G
    with alpha 255, every other pixel is transparent.
    """
    width, height = size
    rgba = np.zeros((height, width, 4), np.uint8)
    if surfaces:
        centre, span = _framing(bounds, pose)
        draw_surface_ids(
            rgba.reshape(-1, 4),
            size,
            surfaces,
            lambda part: _project_points(part, pose, centre, span, size)[:2],
        )
    return png_base64(rgba)


def render_cloud_view(
    points: NDArray[np.float32],
    colors: NDArray[np.uint8],
    pose: CloudPose,
    bounds: Bounds,
    size: tuple[int, int] = CLOUD_VIEW_PX,
    surfaces: SurfaceLayer = (),
) -> str:
    """Every map point rendered server-side from `pose`, as base64 PNG.

    The 3D sibling of `render_floor_plan`: same contract — the whole
    cloud, no sampling (so nothing flickers between updates), a
    deterministic function of (cloud, pose). Only the projection
    differs: an orbit camera instead of top-down. Nearest point wins
    each pixel. Background matches the old WebGL clear colour.
    """
    width, height = size
    rgba = np.zeros((height, width, 4), np.uint8)
    rgba[:, :] = (10, 12, 14, 255)
    if len(points) or surfaces:
        centre, span = _framing(bounds, pose)
        flat = rgba.reshape(-1, 4)
        if len(points):
            ui, vi, depth, indices = _project_points(points, pose, centre, span, size)
            order = np.argsort(depth)[::-1]  # far first; near overwrites
            pixels = (vi[order] * width + ui[order]).astype(np.int64)
            chosen = indices[order]
            flat[pixels, 0] = colors[chosen, 0]
            flat[pixels, 1] = colors[chosen, 1]
            flat[pixels, 2] = colors[chosen, 2]
            flat[pixels, 3] = 255
        draw_surfaces(
            flat, size, surfaces, lambda part: _project_points(part, pose, centre, span, size)[:2]
        )
    return png_base64(rgba)


@dataclass(frozen=True)
class _Scene:
    points: NDArray[np.float32]
    colors: NDArray[np.uint8]
    bounds: Bounds
    layer: SurfaceLayer


class CloudViewer:
    """The console session's 3D view (see module docs); safe across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pose = CloudPose()
        self._surfaces_visible = True
        self._version = 0
        self._scene: _Scene | None = None

    @property
    def version(self) -> int:
        """Bumps on every pose or visibility change, so a player redraws."""
        return self._version

    @property
    def surfaces_visible(self) -> bool:
        return self._surfaces_visible

    def pose(self) -> CloudPose:
        with self._lock:
            return self._pose

    def _set(self, pose: CloudPose) -> CloudPose:
        with self._lock:
            self._pose = pose
            self._version += 1
            return pose

    def orbit(self, d_azimuth: float, d_elevation: float) -> CloudPose:
        pose = self.pose()
        elevation = max(-1.5, min(1.5, pose.elevation + d_elevation))
        return self._set(replace(pose, azimuth=pose.azimuth + d_azimuth, elevation=elevation))

    def zoom(self, factor: float) -> CloudPose:
        pose = self.pose()
        return self._set(replace(pose, zoom=max(0.2, min(20.0, pose.zoom * factor))))

    def pan(self, dx: float, dz: float) -> CloudPose:
        pose = self.pose()
        return self._set(replace(pose, pan_x=pose.pan_x + dx, pan_z=pose.pan_z + dz))

    def reset(self) -> CloudPose:
        return self._set(CloudPose())

    def set_surfaces_visible(self, visible: bool | None) -> None:
        """Show, hide (or, with None, toggle) the surface layer."""
        with self._lock:
            self._surfaces_visible = (not self._surfaces_visible) if visible is None else visible
            self._version += 1

    def shown_surfaces(self, layer: SurfaceLayer) -> SurfaceLayer:
        return layer if self._surfaces_visible else ()

    def render(
        self,
        points: NDArray[np.float32],
        colors: NDArray[np.uint8],
        bounds: Bounds,
        layer: SurfaceLayer,
    ) -> str:
        """Draw a scene from the current pose and remember it for `rerender`."""
        with self._lock:
            self._scene = _Scene(points, colors, bounds, layer)
        return self._draw(self._scene)

    def render_view(
        self,
        points: NDArray[np.float32],
        colors: NDArray[np.uint8],
        bounds: Bounds,
        layer: SurfaceLayer,
    ) -> dict[str, str]:
        """`render`, plus its id image: `cloud_png` and `cloud_ids_png`."""
        cloud_png = self.render(points, colors, bounds, layer)
        return {"cloud_png": cloud_png, "cloud_ids_png": self._ids(bounds, layer)}

    def rerender(self) -> str | None:
        """The last scene drawn again from the current pose; None before any."""
        view = self.rerender_view()
        return None if view is None else view["cloud_png"]

    def rerender_view(self) -> dict[str, str] | None:
        """`rerender`, plus its id image; None before any scene."""
        with self._lock:
            scene = self._scene
        if scene is None:
            return None
        return {
            "cloud_png": self._draw(scene),
            "cloud_ids_png": self._ids(scene.bounds, scene.layer),
        }

    def _ids(self, bounds: Bounds, layer: SurfaceLayer) -> str:
        return render_cloud_ids(self.pose(), bounds, surfaces=self.shown_surfaces(layer))

    def _draw(self, scene: _Scene) -> str:
        return render_cloud_view(
            scene.points,
            scene.colors,
            self.pose(),
            scene.bounds,
            surfaces=self.shown_surfaces(scene.layer),
        )
