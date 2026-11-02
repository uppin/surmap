"""The 3D pane: its server-side render and the console session's view of it.

`render_cloud_view` draws every map point from a `CloudPose` (an orbit
camera), nearest point per pixel, with the SAM surface layer over it.
`render_cloud_ids` draws the same surface pixels as an id image: which
surface each pixel shows, for hover picking. The projection keeps the map
frame's handedness (its y points down), so the right of a camera is drawn
on the right.

`CloudViewer` is the pane's state for the whole console session, not for
one run: the PTZ pose, whether surfaces are shown, whether the view
follows the camera, a version that bumps on every change, and the last
scene it drew. Every run's `PlaybackControls` uses the server's one
viewer, so a pose set during a run (or with nothing playing) is the pose
of the next. A PTZ action answers with `rerender_view()`: the last scene
drawn again from the new pose, so the pane moves after a run has finished
or on a scrubbed moment, not only with the next map update.

Follow (on by default) frames a scene like a navigation app. A scene
carries the camera it was drawn for (the shown frame's floor camera: its
position and unit heading on the x-z floor). The view looks along that
heading from behind the camera, at the pose's tilt, and the camera sits at
3/4 of the image height so a quarter of the view is the scene behind it,
at any tilt and zoom; `FOLLOW_SPAN_M` of scene fills the view at zoom 1. Tilt
and zoom adjust the follow view; an orbit or a pan takes over, starting
from the exact follow view, and turns Follow off. Without a camera the
follow view is the free one. A yellow arrow marks the camera in both.
"""

from __future__ import annotations

import base64
import io
import math
import threading
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from surmap.demo.surface_render import SurfaceLayer, draw_surface_ids, draw_surfaces

Bounds = tuple[NDArray[np.float32], NDArray[np.float32]]
# The shown frame's camera on the floor: x, z, unit heading dx, dz (`floor_camera`).
FollowCamera = dict[str, float]

CLOUD_VIEW_PX = (880, 440)
FOLLOW_SPAN_M = 24.0
CAMERA_MARKER = (255, 210, 60)
_FOCAL = 1.0 / math.tan(0.35)
_DISTANCE_PER_SPAN = 1.9
_CAMERA_ROW = 0.75  # where the followed camera sits, as a fraction of the image height


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


@dataclass(frozen=True)
class _Framing:
    """How a view is drawn: the orbit pose, the point it orbits, and its span."""

    pose: CloudPose
    centre: NDArray[np.float64]
    span: float


def _project(
    points: NDArray[np.float32] | NDArray[np.float64], framing: _Framing, size: tuple[int, int]
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_]]:
    """Map-frame points to float (u, v, depth) and whether each is in front of the view."""
    width, height = size
    pose = framing.pose
    rel = points.astype(np.float64).reshape(-1, 3) - framing.centre
    x, up, fwd = rel[:, 0], -rel[:, 1], rel[:, 2]
    ca, sa = math.cos(pose.azimuth), math.sin(pose.azimuth)
    x, fwd = x * ca - fwd * sa, x * sa + fwd * ca
    ce, se = math.cos(pose.elevation), math.sin(pose.elevation)
    up, fwd = up * ce - fwd * se, up * se + fwd * ce
    distance = framing.span * _DISTANCE_PER_SPAN * pose.zoom
    depth = distance - fwd
    ahead = depth > distance * 0.05
    safe = np.where(ahead, depth, 1.0)
    # (x, -y, z) is left-handed: u runs against x so the image is not mirrored.
    u = width / 2 - _FOCAL * x / safe * (height / 2)
    v = height / 2 - _FOCAL * up / safe * (height / 2)
    return u, v, depth, ahead


def _project_points(
    points: NDArray[np.float32], framing: _Framing, size: tuple[int, int]
) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64], NDArray[np.int64]]:
    """Map-frame points to on-image (u, v, depth, point indices)."""
    width, height = size
    u, v, depth, ahead = _project(points, framing, size)
    indices = np.flatnonzero(ahead)
    ui, vi = np.floor(u[ahead]).astype(np.int64), np.floor(v[ahead]).astype(np.int64)
    on = (ui >= 0) & (ui < width) & (vi >= 0) & (vi < height)
    return ui[on], vi[on], depth[ahead][on], indices[on]


def _free_framing(bounds: Bounds, pose: CloudPose) -> _Framing:
    """The free view of `bounds`: orbiting their (panned) centre, spanning them."""
    lo, hi = (np.asarray(bound, dtype=np.float64) for bound in bounds)
    centre = (lo + hi) / 2.0
    centre[0] += pose.pan_x
    centre[2] += pose.pan_z
    return _Framing(pose, centre, max(float(np.max(hi - lo)), 0.5))


def _follow_framing(bounds: Bounds, pose: CloudPose, camera: FollowCamera) -> _Framing:
    """The chase view of `camera`: from behind it along its heading, at the pose's tilt."""
    dx, dz = float(camera["dx"]), float(camera["dz"])
    length = math.hypot(dx, dz) or 1.0
    dx, dz = dx / length, dz / length
    elevation = max(0.15, min(1.45, pose.elevation))
    # The orbit point sits this far ahead of the camera, so the camera lands at
    # _CAMERA_ROW of the image: focal * a * sin(e) / (distance - a * cos(e)) = 2 * row - 1.
    distance = FOLLOW_SPAN_M * _DISTANCE_PER_SPAN * pose.zoom
    below = 2 * _CAMERA_ROW - 1
    ahead_m = below * distance / (_FOCAL * math.sin(elevation) + below * math.cos(elevation))
    lo, hi = (np.asarray(bound, dtype=np.float64) for bound in bounds)
    centre = np.array(
        [camera["x"] + dx * ahead_m, (lo[1] + hi[1]) / 2.0, camera["z"] + dz * ahead_m]
    )
    follow = CloudPose(azimuth=math.atan2(-dx, -dz), elevation=elevation, zoom=pose.zoom)
    return _Framing(follow, centre, FOLLOW_SPAN_M)


def _draw_camera(rgba: NDArray[np.uint8], framing: _Framing, camera: FollowCamera) -> None:
    """A yellow arrow at the camera, pointing along its heading."""
    dx, dz = float(camera["dx"]), float(camera["dz"])
    length = math.hypot(dx, dz) or 1.0
    dx, dz = dx / length, dz / length
    y = float(framing.centre[1])
    x, z = float(camera["x"]), float(camera["z"])
    size_m = max(1.0, framing.span / 24.0)
    corners = np.array(
        [
            [x + dx * 2.5 * size_m, y, z + dz * 2.5 * size_m],  # the tip, ahead
            [x + dz * size_m, y, z - dx * size_m],  # its right
            [x - dz * size_m, y, z + dx * size_m],  # its left
        ]
    )
    height, width = rgba.shape[:2]
    u, v, _, ahead = _project(corners, framing, (width, height))
    if not ahead.all():
        return
    image = Image.fromarray(rgba, "RGBA")
    ImageDraw.Draw(image).polygon(
        [(float(a), float(b)) for a, b in zip(u, v, strict=True)], fill=(*CAMERA_MARKER, 255)
    )
    rgba[:] = np.asarray(image)


def _render(
    points: NDArray[np.float32],
    colors: NDArray[np.uint8],
    framing: _Framing,
    size: tuple[int, int],
    surfaces: SurfaceLayer,
    camera: FollowCamera | None,
) -> str:
    width, height = size
    rgba = np.zeros((height, width, 4), np.uint8)
    rgba[:, :] = (10, 12, 14, 255)
    flat = rgba.reshape(-1, 4)
    if len(points):
        ui, vi, depth, indices = _project_points(points, framing, size)
        order = np.argsort(depth)[::-1]  # far first; near overwrites
        pixels = (vi[order] * width + ui[order]).astype(np.int64)
        chosen = indices[order]
        flat[pixels, 0] = colors[chosen, 0]
        flat[pixels, 1] = colors[chosen, 1]
        flat[pixels, 2] = colors[chosen, 2]
        flat[pixels, 3] = 255
    draw_surfaces(flat, size, surfaces, lambda part: _project_points(part, framing, size)[:2])
    if camera is not None:
        _draw_camera(rgba, framing, camera)
    return png_base64(rgba)


def _render_ids(framing: _Framing, size: tuple[int, int], surfaces: SurfaceLayer) -> str:
    width, height = size
    rgba = np.zeros((height, width, 4), np.uint8)
    draw_surface_ids(
        rgba.reshape(-1, 4), size, surfaces, lambda part: _project_points(part, framing, size)[:2]
    )
    return png_base64(rgba)


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
    return _render_ids(_free_framing(bounds, pose), size, surfaces)


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
    return _render(points, colors, _free_framing(bounds, pose), size, surfaces, None)


@dataclass(frozen=True)
class _Scene:
    points: NDArray[np.float32]
    colors: NDArray[np.uint8]
    bounds: Bounds
    layer: SurfaceLayer
    camera: FollowCamera | None


class CloudViewer:
    """The console session's 3D view (see module docs); safe across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pose = CloudPose()
        self._surfaces_visible = True
        self._follow = True
        self._version = 0
        self._scene: _Scene | None = None

    @property
    def version(self) -> int:
        """Bumps on every pose, visibility or follow change, so a player redraws."""
        return self._version

    @property
    def surfaces_visible(self) -> bool:
        return self._surfaces_visible

    @property
    def follow(self) -> bool:
        return self._follow

    @property
    def camera(self) -> FollowCamera | None:
        """The camera the last scene was drawn for."""
        with self._lock:
            return None if self._scene is None else self._scene.camera

    def pose(self) -> CloudPose:
        with self._lock:
            return self._pose

    def _set(self, pose: CloudPose) -> CloudPose:
        with self._lock:
            self._pose = pose
            self._version += 1
            return pose

    def set_follow(self, follow: bool) -> None:
        with self._lock:
            self._follow = follow
            self._version += 1

    def _take_over(self) -> CloudPose:
        """Leave Follow for the free view that shows exactly what Follow showed."""
        with self._lock:
            pose, scene, following = self._pose, self._scene, self._follow
            self._follow = False
        if not following or scene is None or scene.camera is None:
            return pose
        followed = _follow_framing(scene.bounds, pose, scene.camera)
        free = _free_framing(scene.bounds, CloudPose())
        return self._set(
            replace(
                followed.pose,
                zoom=followed.pose.zoom * followed.span / free.span,
                pan_x=float(followed.centre[0] - free.centre[0]),
                pan_z=float(followed.centre[2] - free.centre[2]),
            )
        )

    def orbit(self, d_azimuth: float, d_elevation: float) -> CloudPose:
        """Turn and tilt; turning takes over from Follow, tilting adjusts it."""
        pose = self._take_over() if d_azimuth else self.pose()
        elevation = max(-1.5, min(1.5, pose.elevation + d_elevation))
        return self._set(replace(pose, azimuth=pose.azimuth + d_azimuth, elevation=elevation))

    def zoom(self, factor: float) -> CloudPose:
        pose = self.pose()
        return self._set(replace(pose, zoom=max(0.2, min(20.0, pose.zoom * factor))))

    def pan(self, dx: float, dz: float) -> CloudPose:
        """Pan the free view; panning takes over from Follow."""
        pose = self._take_over()
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
        camera: FollowCamera | None = None,
    ) -> str:
        """Draw a scene from the current view and remember it for `rerender`."""
        return self.render_view(points, colors, bounds, layer, camera)["cloud_png"]

    def render_view(
        self,
        points: NDArray[np.float32],
        colors: NDArray[np.uint8],
        bounds: Bounds,
        layer: SurfaceLayer,
        camera: FollowCamera | None = None,
    ) -> dict[str, str]:
        """`render`, plus its id image: `cloud_png` and `cloud_ids_png`."""
        scene = _Scene(points, colors, bounds, layer, camera)
        with self._lock:
            self._scene = scene
        return self._draw(scene)

    def rerender(self) -> str | None:
        """The last scene drawn again from the current view; None before any."""
        view = self.rerender_view()
        return None if view is None else view["cloud_png"]

    def rerender_view(self) -> dict[str, str] | None:
        """`rerender`, plus its id image; None before any scene."""
        with self._lock:
            scene = self._scene
        return None if scene is None else self._draw(scene)

    def _framing(self, scene: _Scene) -> _Framing:
        pose = self.pose()
        if self._follow and scene.camera is not None:
            return _follow_framing(scene.bounds, pose, scene.camera)
        return _free_framing(scene.bounds, pose)

    def _draw(self, scene: _Scene) -> dict[str, str]:
        framing = self._framing(scene)
        layer = self.shown_surfaces(scene.layer)
        return {
            "cloud_png": _render(
                scene.points, scene.colors, framing, CLOUD_VIEW_PX, layer, scene.camera
            ),
            "cloud_ids_png": _render_ids(framing, CLOUD_VIEW_PX, layer),
        }
