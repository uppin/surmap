"""Dense stereo for masks the sparse RTAB-Map cloud does not reach.

RTAB-Map keeps only keyframe feature points. A low-texture shirt or a
rubble pile can get none, and ``points_in_mask`` then claims nothing for
that mask. ``DenseStereoFallback`` reconstructs the frame's own stereo
pair with the pure-NumPy ``surmap.survey.stereo`` matcher and returns
camera-frame points in the same optical convention as the sparse cloud
after ``to_camera_frame`` (x right, y down, z forward). Passing them to
``points_in_mask(..., pose)`` puts them in the map frame exactly like
the sparse points.

Matcher convention: ``surmap.survey.stereo`` pairs left pixel ``x`` with
right pixel ``x + d``. The Gazebo rig (left eye at +Y, right at -Y in
``docs/simulation/gz/surmap_stereo_cam/model.sdf``) has the textbook
geometry, right pixel ``x - d``. Both images are therefore also matched
mirrored (which turns ``x - d`` into ``x + d``) and the result with more
points is kept. One reconstruction per frame is cached, so several masks
in one frame share it.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from surmap.survey.stereo import FrameImage, StereoReconstructor, StereoRig
from surmap.types import StereoFramePair, Vec3

STEREO_FALLBACK = "stereo-fallback"
SPARSE_RTABMAP = "sparse-rtabmap"


class DenseStereoFallback:
    def __init__(
        self,
        rig: StereoRig,
        width: int,
        height: int,
        *,
        max_depth_m: float,
        min_disparity_px: float,
        reconstructor: StereoReconstructor | None = None,
    ) -> None:
        self._rig = rig
        self._width = width
        self._height = height
        depth = max_depth_m
        if min_disparity_px > 0:
            depth = min(depth, rig.fx * rig.baseline_m / min_disparity_px)
        self._max_depth_m = depth
        self._stereo = (
            reconstructor
            if reconstructor is not None
            else StereoReconstructor(max_depth_m=depth, stride=1, match_width_px=320)
        )
        self._cached: tuple[int, tuple[Vec3, ...]] | None = None
        self.reconstructions = 0

    @property
    def max_depth_m(self) -> float:
        return self._max_depth_m

    def camera_points(self, frame: StereoFramePair) -> tuple[Vec3, ...]:
        """Camera-frame dense points for ``frame``, reconstructed once per frame."""
        if self._cached is not None and self._cached[0] == frame.frame_id:
            return self._cached[1]
        left = _image_bytes(frame.left_data, frame.left_ref)
        right = _image_bytes(frame.right_data, frame.right_ref)
        try:
            points = self._reconstruct(left, right)
        except ValueError:
            points = ()
        self.reconstructions += 1
        self._cached = (frame.frame_id, points)
        return points

    def _reconstruct(self, left: bytes, right: bytes) -> tuple[Vec3, ...]:
        native = self._stereo.reconstruct(self._frame(left), self._frame(right), self._rig)
        mirrored_rig = StereoRig(
            self._rig.fx,
            self._rig.fy,
            (self._width - 1) - self._rig.cx,
            self._rig.cy,
            self._rig.baseline_m,
        )
        mirrored = self._stereo.reconstruct(
            self._frame(_mirror(left)), self._frame(_mirror(right)), mirrored_rig
        )
        textbook = tuple(Vec3(-point.x, point.y, point.z) for point in mirrored)
        chosen = textbook if len(textbook) >= len(native) else native
        return tuple(point for point in chosen if point.z <= self._max_depth_m)

    def _frame(self, data: bytes) -> FrameImage:
        return FrameImage(self._width, self._height, "mjpeg", data)


def _image_bytes(data: bytes, ref: str) -> bytes:
    return data if data else Path(ref).read_bytes()


def _mirror(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as image:
        flipped = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        out = io.BytesIO()
        flipped.save(out, format="PNG")
    return out.getvalue()
