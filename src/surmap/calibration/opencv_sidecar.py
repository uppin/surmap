"""OpenCV sidecar for checkerboard vision.

Two halves over one protocol (one JSON object per line):

- Server: `python -m surmap.calibration.opencv_sidecar` reads requests
  on stdin and writes replies on stdout. It is the only place `cv2`
  is imported. Ops: `detect` (one frame -> corners or null) and
  `calibrate` (all views -> stereo estimate, pinhole radial-tangential,
  rational or fisheye). This mirrors
  RTAB-Map's own calibration (`guilib/src/CalibrationDialog.cpp`:
  `findChessboardCorners` -> `cornerSubPix` with a window of half the
  corner spacing -> `calibrateCamera` per eye -> `stereoCalibrate`
  with fixed intrinsics) without the GUI or live-camera ownership.
  Where RTAB-Map drops single corners that drift during refinement,
  this drops the whole board: views here are dense row-major grids.
- Client: `OpenCvSidecarVision` spawns that process and speaks the
  protocol, satisfying the `CheckerboardVision` port. Frames cross
  as base64 raw-RGB (calibration runs at view rate, not video rate).

Without `cv2`, the server replies `{"error": "opencv unavailable: ..."}`
and the client raises `CalibrationUnavailable` naming the install.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
from dataclasses import dataclass
from typing import Any

from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.port import (
    CalibrationUnavailable,
    CalibrationView,
    CornerSet,
    LensModel,
    StereoEstimate,
    UnreadableFrame,
)

INSTALL_HINT = (
    "OpenCV is not importable in the calibration sidecar. Install the "
    "sidecar environment with opencv-python-headless (see "
    "src/surmap/calibration/opencv_sidecar.py), or run the RPC with a "
    "different CheckerboardVision adapter."
)


def _load_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise CalibrationUnavailable(f"{INSTALL_HINT} ({exc})") from exc
    return cv2


def decode_rgb(width: int, height: int, encoding: str, data: bytes) -> Any:
    """One frame as a grayscale numpy array (sidecar side)."""
    import numpy as np

    if encoding == "raw_rgb":
        arr = np.frombuffer(data, dtype=np.uint8)
        if arr.size != width * height * 3:
            raise ValueError(f"raw_rgb frame has {arr.size} bytes, expected {width * height * 3}")
        rgb = arr.reshape(height, width, 3)
        return rgb.mean(axis=2).astype(np.uint8)
    # MJPEG/JPEG/PNG bytes: let OpenCV decode.
    cv2 = _load_cv2()
    import numpy as np

    buf = np.frombuffer(data, dtype=np.uint8)
    gray: Any = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("undecodable frame bytes")
    return gray


MAX_SUBPIXEL_DRIFT_PX = 1.0
"""RTAB-Map's default sub-pixel error bound: a corner refined further
than this was pulled by glare or a neighbour, so the board is dropped."""


def subpixel_half_window(points: Any) -> int:
    """Half the smallest spacing between consecutive corners (RTAB-Map).

    A fixed window wider than the squares lets refinement jump onto the
    neighbouring corner on a small or distant board.
    """
    import numpy as np

    flat = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    spacing = float(np.min(np.linalg.norm(np.diff(flat, axis=0), axis=1)))
    return max(2, int(spacing / 2))


def _find_chessboard(gray: Any, board: CheckerboardSpec, max_scale: int) -> Any | None:
    """Coarse corners in native pixels, trying 1x .. `max_scale`x (RTAB-Map)."""
    cv2 = _load_cv2()
    import numpy as np

    pattern = (board.cols, board.rows)
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
    for scale in range(1, max_scale + 1):
        image = gray
        if scale > 1:
            image = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        found, corners = cv2.findChessboardCorners(image, pattern, flags)
        if found:
            # Pixel centres: upscaled p sits at (p + 0.5) / scale − 0.5 natively.
            scaled = np.asarray(corners, dtype=np.float32).reshape(-1, 1, 2)
            return (scaled + 0.5) / scale - 0.5
    return None


def detect_corners(gray: Any, board: CheckerboardSpec, max_scale: int = 1) -> CornerSet | None:
    cv2 = _load_cv2()
    import numpy as np

    coarse = _find_chessboard(gray, board, max_scale)
    if coarse is not None:
        coarse = coarse.astype(np.float32)
        half = subpixel_half_window(coarse)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01)
        refined = cv2.cornerSubPix(gray, coarse.copy(), (half, half), (-1, -1), criteria)
        drift = np.linalg.norm((refined - coarse).reshape(-1, 2), axis=1)
        if float(drift.max()) > MAX_SUBPIXEL_DRIFT_PX:
            return None
        points = refined
    else:
        # The sector-based detector returns sub-pixel corners itself.
        found, corners = cv2.findChessboardCornersSB(
            gray, (board.cols, board.rows), cv2.CALIB_CB_NORMALIZE_IMAGE
        )
        if not found or corners is None:
            return None
        points = corners
    flat = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    return tuple((float(p[0]), float(p[1])) for p in flat)


_STEREO_CRITERIA = (3, 100, 1e-5)  # COUNT + EPS, as RTAB-Map's stereo solve
MIN_FISHEYE_VIEWS = 4
"""Fewest views the fisheye solve may prune down to."""

_ILL_CONDITIONED = re.compile(r"input array (\d+)")


@dataclass(frozen=True)
class _Eye:
    rms: float
    camera: Any
    distortion: Any


def _pinhole_eye(obj: list[Any], points: list[Any], size: tuple[int, int], flags: int) -> _Eye:
    cv2 = _load_cv2()
    rms, camera, distortion, _, _ = cv2.calibrateCamera(obj, points, size, None, None, flags=flags)
    return _Eye(float(rms), camera, distortion)


def _fisheye_flag(name: str) -> int:
    """A fisheye flag: `cv2.fisheye.*` on OpenCV 4, `cv2.*` on OpenCV 5.

    The two namespaces' values differ on OpenCV 4, so the fisheye one is
    preferred whenever it exists.
    """
    cv2 = _load_cv2()
    flag = getattr(cv2.fisheye, name, None)
    value: int = flag if flag is not None else getattr(cv2, name)
    return value


def _fisheye_eye(
    obj: list[Any], points: list[Any], size: tuple[int, int]
) -> tuple[_Eye, list[int]]:
    """cv::fisheye::calibrate, pruning ill-conditioned views as RTAB-Map does.

    CALIB_CHECK_COND throws on the first ill-conditioned view and names
    it ("... input array 43"); that view is dropped and the solve retried
    while at least `MIN_FISHEYE_VIEWS` remain. Returns the kept indices.
    """
    cv2 = _load_cv2()
    kept = list(range(len(obj)))
    flags = (
        _fisheye_flag("CALIB_RECOMPUTE_EXTRINSIC")
        | _fisheye_flag("CALIB_CHECK_COND")
        | _fisheye_flag("CALIB_FIX_SKEW")
    )
    while True:
        try:
            rms, camera, distortion, _, _ = cv2.fisheye.calibrate(
                [obj[i] for i in kept], [points[i] for i in kept], size, None, None, flags=flags
            )
            return _Eye(float(rms), camera, distortion), kept
        except cv2.error as exc:
            match = _ILL_CONDITIONED.search(str(exc))
            if match is None or len(kept) <= MIN_FISHEYE_VIEWS:
                raise
            del kept[int(match.group(1))]


def calibrate_views(
    views: tuple[CalibrationView, ...],
    board: CheckerboardSpec,
    width: int,
    height: int,
    lens: LensModel = LensModel.PINHOLE_RADTAN,
) -> StereoEstimate:
    """RTAB-Map's solve: each eye alone, then the extrinsic with intrinsics fixed."""
    cv2 = _load_cv2()
    import numpy as np

    fisheye = lens is LensModel.FISHEYE
    # cv::fisheye takes float64 points laid out 1xN (OpenCV 5 rejects Nx1).
    dtype = np.float64 if fisheye else np.float32
    layout = (1, -1) if fisheye else (-1, 1)
    obj = [np.array(board.object_points(), dtype=dtype).reshape(*layout, 3) for _ in views]
    left_pts = [np.array(v.left, dtype=dtype).reshape(*layout, 2) for v in views]
    right_pts = [np.array(v.right, dtype=dtype).reshape(*layout, 2) for v in views]
    size = (width, height)
    if fisheye:
        left, kept_left = _fisheye_eye(obj, left_pts, size)
        right, kept_right = _fisheye_eye(obj, right_pts, size)
        both = sorted(set(kept_left) & set(kept_right))
        stereo = cv2.fisheye.stereoCalibrate(
            [obj[i] for i in both],
            [left_pts[i] for i in both],
            [right_pts[i] for i in both],
            left.camera,
            left.distortion,
            right.camera,
            right.distortion,
            size,
            flags=_fisheye_flag("CALIB_FIX_INTRINSIC"),
            criteria=_STEREO_CRITERIA,
        )
        rms_s, rot, trans, views_used = stereo[0], stereo[5], stereo[6], len(both)
        coefficients = 4
    else:
        # Radial-tangential holds k3 at 0: the EuRoC model SurMap exports
        # carries k1, k2, p1, p2 only. Rational solves all eight.
        model = cv2.CALIB_RATIONAL_MODEL if lens is LensModel.PINHOLE_RATIONAL else cv2.CALIB_FIX_K3
        left = _pinhole_eye(obj, left_pts, size, model)
        right = _pinhole_eye(obj, right_pts, size, model)
        stereo = cv2.stereoCalibrate(
            obj,
            left_pts,
            right_pts,
            left.camera,
            left.distortion,
            right.camera,
            right.distortion,
            size,
            criteria=_STEREO_CRITERIA,
            flags=cv2.CALIB_FIX_INTRINSIC | model,
        )
        rms_s, rot, trans, views_used = stereo[0], stereo[5], stereo[6], len(views)
        coefficients = 8 if lens is LensModel.PINHOLE_RATIONAL else 4
    kl, kr = left.camera, right.camera
    t = np.asarray(trans, dtype=np.float64).ravel()
    return StereoEstimate(
        left_fx=float(kl[0, 0]),
        left_fy=float(kl[1, 1]),
        left_cx=float(kl[0, 2]),
        left_cy=float(kl[1, 2]),
        right_fx=float(kr[0, 0]),
        right_fy=float(kr[1, 1]),
        right_cx=float(kr[0, 2]),
        right_cy=float(kr[1, 2]),
        distortion_left=tuple(float(x) for x in np.ravel(left.distortion)[:coefficients]),
        distortion_right=tuple(float(x) for x in np.ravel(right.distortion)[:coefficients]),
        rotation=tuple(float(x) for x in np.asarray(rot, dtype=np.float64).ravel()),
        translation_m=(float(t[0]), float(t[1]), float(t[2])),
        baseline_m=float(np.linalg.norm(t)),
        rms_left=left.rms,
        rms_right=right.rms,
        rms_stereo=float(rms_s),
        views_used=views_used,
        lens=lens,
    )


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    """One sidecar protocol request -> reply (pure, testable)."""
    op = request.get("op")
    board = CheckerboardSpec(
        cols=int(request["cols"]),
        rows=int(request["rows"]),
        square_size_m=float(request["square_size_m"]),
    )
    if op == "detect":
        try:
            gray = decode_rgb(
                int(request["width"]),
                int(request["height"]),
                str(request.get("encoding", "raw_rgb")),
                base64.b64decode(str(request["data_b64"])),
            )
        except ValueError as exc:
            return {"unreadable": str(exc)}
        corners = detect_corners(gray, board, int(request.get("max_scale", 1)))
        return {"corners": [list(p) for p in corners] if corners else None}
    if op == "calibrate":
        views = tuple(
            CalibrationView(
                left=tuple((float(x), float(y)) for x, y in v["left"]),
                right=tuple((float(x), float(y)) for x, y in v["right"]),
            )
            for v in request["views"]
        )
        est = calibrate_views(
            views,
            board,
            int(request["width"]),
            int(request["height"]),
            LensModel(str(request.get("lens", LensModel.PINHOLE_RADTAN.value))),
        )
        return {
            "estimate": {
                "left_fx": est.left_fx,
                "left_fy": est.left_fy,
                "left_cx": est.left_cx,
                "left_cy": est.left_cy,
                "right_fx": est.right_fx,
                "right_fy": est.right_fy,
                "right_cx": est.right_cx,
                "right_cy": est.right_cy,
                "distortion_left": list(est.distortion_left),
                "distortion_right": list(est.distortion_right),
                "rotation": list(est.rotation),
                "translation_m": list(est.translation_m),
                "baseline_m": est.baseline_m,
                "rms_left": est.rms_left,
                "rms_right": est.rms_right,
                "rms_stereo": est.rms_stereo,
                "views_used": est.views_used,
                "lens": est.lens.value,
            }
        }
    return {"error": f"unknown op {op!r}"}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = handle_request(json.loads(line))
        except Exception as exc:  # sidecar replies, never dies on one view
            reply = {"error": str(exc)}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()
    return 0


class OpenCvSidecarVision:
    """`CheckerboardVision` over a spawned OpenCV sidecar process."""

    def __init__(self, argv: list[str] | None = None) -> None:
        self._argv = argv or [sys.executable, "-m", "surmap.calibration.opencv_sidecar"]
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    async def _roundtrip(self, request: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            if self._proc is None or self._proc.returncode is not None:
                self._proc = await asyncio.create_subprocess_exec(
                    *self._argv,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                )
            assert self._proc.stdin is not None and self._proc.stdout is not None
            self._proc.stdin.write((json.dumps(request) + "\n").encode())
            await self._proc.stdin.drain()
            line = await self._proc.stdout.readline()
            if not line:
                raise CalibrationUnavailable("calibration sidecar exited without a reply")
            reply: dict[str, Any] = json.loads(line)
            if "error" in reply:
                raise CalibrationUnavailable(str(reply["error"]))
            if "unreadable" in reply:
                raise UnreadableFrame(str(reply["unreadable"]))
            return reply

    async def detect(
        self,
        *,
        frame_id: int,
        width: int,
        height: int,
        encoding: str,
        data: bytes,
        board: CheckerboardSpec,
        max_scale: int,
    ) -> CornerSet | None:
        reply = await self._roundtrip(
            {
                "op": "detect",
                "width": width,
                "height": height,
                "encoding": encoding,
                "data_b64": base64.b64encode(data).decode(),
                "max_scale": max_scale,
                "cols": board.cols,
                "rows": board.rows,
                "square_size_m": board.square_size_m,
            }
        )
        corners = reply.get("corners")
        if corners is None:
            return None
        return tuple((float(x), float(y)) for x, y in corners)

    async def calibrate(
        self,
        *,
        views: tuple[CalibrationView, ...],
        board: CheckerboardSpec,
        width: int,
        height: int,
        lens: LensModel,
    ) -> StereoEstimate:
        reply = await self._roundtrip(
            {
                "op": "calibrate",
                "lens": lens.value,
                "width": width,
                "height": height,
                "cols": board.cols,
                "rows": board.rows,
                "square_size_m": board.square_size_m,
                "views": [
                    {"left": [list(p) for p in v.left], "right": [list(p) for p in v.right]}
                    for v in views
                ],
            }
        )
        e = reply["estimate"]
        return StereoEstimate(
            left_fx=e["left_fx"],
            left_fy=e["left_fy"],
            left_cx=e["left_cx"],
            left_cy=e["left_cy"],
            right_fx=e["right_fx"],
            right_fy=e["right_fy"],
            right_cx=e["right_cx"],
            right_cy=e["right_cy"],
            distortion_left=tuple(e["distortion_left"]),
            distortion_right=tuple(e["distortion_right"]),
            rotation=tuple(e["rotation"]),
            translation_m=(e["translation_m"][0], e["translation_m"][1], e["translation_m"][2]),
            baseline_m=e["baseline_m"],
            rms_left=e["rms_left"],
            rms_right=e["rms_right"],
            rms_stereo=e["rms_stereo"],
            views_used=e["views_used"],
            lens=LensModel(e["lens"]),
        )

    async def close(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            await self._proc.wait()
        self._proc = None


if __name__ == "__main__":
    raise SystemExit(main())
