from __future__ import annotations

import threading

from surmap.demo.cloud_view import CloudPose, CloudViewer
from surmap.demo.surface_render import SurfaceLayer


class PlaybackControls:
    """Pause, resume or cancel one player from another thread.

    Its 3D view is the session's `CloudViewer` (a fresh one when none is
    given), so every run of one console shares the pose.
    """

    def __init__(self, viewer: CloudViewer | None = None) -> None:
        self._playing = threading.Event()
        self._playing.set()
        self._cancelled = threading.Event()
        self.viewer = viewer if viewer is not None else CloudViewer()

    @property
    def paused(self) -> bool:
        return not self._playing.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def pause(self) -> None:
        self._playing.clear()

    def resume(self) -> None:
        self._playing.set()

    def cancel(self) -> None:
        self._cancelled.set()
        self._playing.set()  # a paused player wakes up to stop

    def wait_while_paused(self, timeout: float) -> None:
        self._playing.wait(timeout)

    @property
    def cloud_version(self) -> int:
        return self.viewer.version

    def cloud_pose(self) -> CloudPose:
        return self.viewer.pose()

    def cloud_orbit(self, d_azimuth: float, d_elevation: float) -> CloudPose:
        return self.viewer.orbit(d_azimuth, d_elevation)

    def cloud_zoom(self, factor: float) -> CloudPose:
        return self.viewer.zoom(factor)

    def cloud_pan(self, dx: float, dz: float) -> CloudPose:
        return self.viewer.pan(dx, dz)

    def cloud_reset(self) -> CloudPose:
        return self.viewer.reset()

    @property
    def surfaces_visible(self) -> bool:
        return self.viewer.surfaces_visible

    def set_surfaces_visible(self, visible: bool | None) -> None:
        """Show, hide (or, with None, toggle) the surface layer; re-renders the cloud."""
        self.viewer.set_surfaces_visible(visible)

    def shown_surfaces(self, layer: SurfaceLayer) -> SurfaceLayer:
        return self.viewer.shown_surfaces(layer)
