"""Render `tests/fixtures/plane_stereo/`: ten stereo pairs of a photo-textured plane.

The stereo tests' committed pairs. Each pair is the ELP rig (640x480, fx 381.36, 0.07 m baseline)
looking at a tilted plane at tabletop range, so every pixel's true depth is known. The texture is
Poly Haven's `rocks_ground_02` (CC0-1.0, pinned in the simulation's `assets.lock.json`). The right
camera's principal point sits `RIGHT_OFFSET_PX` from the left one's, like a real unrectified rig,
so the pairs also exercise the reconstructor's `alignment_offset`. The second eye sits on the
side `StereoReconstructor` matches against (a match pairs left x with right x + d), as on the
rig's own streams; `surmap.mission.dense` mirrors textbook pairs into that geometry.

Deterministic: rerunning it over the same texture rewrites the same files.

    uv run python scripts/fetch_sim_assets.py
    uv run python scripts/render_plane_stereo_fixture.py
"""

from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
TEXTURE = REPO / "examples" / "bevy-sitl-poc" / "assets" / "textures" / "rocks_ground_02_diff_2k.jpg"
OUT = REPO / "tests" / "fixtures" / "plane_stereo"

WIDTH, HEIGHT = 640, 480
FX = FY = 381.36
CX, CY = 320.0, 240.0
BASELINE_M = 0.07
RIGHT_OFFSET_PX = (10.0, 12.0)
# The 2k texture spans this many metres of the plane (a 2 m patch of rocky ground).
TEXTURE_SPAN_M = 2.0
TILT_DEG, TILT_STEP_DEG = 75.0, 0.5
DEPTH_M, DEPTH_STEP_M = 0.45, 0.005


def _plane(index: int) -> tuple[NDArray[np.float64], float, NDArray[np.float64]]:
    """Unit normal, distance along the optical axis, and in-plane texture shift of pair `index`."""
    # A tabletop seen from above it: the plane recedes toward the top of the image.
    tilt = math.radians(TILT_DEG + TILT_STEP_DEG * index)
    normal = np.array([0.0, -math.cos(tilt), -math.sin(tilt)])
    axis_depth = DEPTH_M + DEPTH_STEP_M * index
    shift = np.array([0.012 * index, 0.008 * index])
    return normal, axis_depth, shift


def _render(
    texture: NDArray[np.float32], index: int, origin_x: float, cx: float, cy: float
) -> NDArray[np.uint8]:
    normal, axis_depth, shift = _plane(index)
    anchor = np.array([0.0, 0.0, axis_depth])
    u, v = np.meshgrid(np.arange(WIDTH, dtype=np.float64), np.arange(HEIGHT, dtype=np.float64))
    rays = np.stack([(u - cx) / FX, (v - cy) / FY, np.ones_like(u)], axis=-1)
    origin = np.array([origin_x, 0.0, 0.0])
    s = float(normal @ (anchor - origin)) / (rays @ normal)
    points = origin + rays * s[..., None]
    across = np.array([1.0, 0.0, 0.0])
    along = np.cross(normal, across)
    local = points - anchor
    tex_px = texture.shape[0] / TEXTURE_SPAN_M
    tx = (local @ across + shift[0]) * tex_px + texture.shape[1] / 2
    ty = (local @ along + shift[1]) * tex_px + texture.shape[0] / 2
    return _bilinear(texture, tx, ty)


def _bilinear(
    texture: NDArray[np.float32], x: NDArray[np.float64], y: NDArray[np.float64]
) -> NDArray[np.uint8]:
    h, w = texture.shape[:2]
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    top = texture[y0, x0] * (1 - fx) + texture[y0, x0 + 1] * fx
    bottom = texture[y0 + 1, x0] * (1 - fx) + texture[y0 + 1, x0 + 1] * fx
    return np.clip(top * (1 - fy) + bottom * fy, 0, 255).astype(np.uint8)


def _jpeg(pixels: NDArray[np.uint8]) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(pixels, "RGB").save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--texture", type=Path, default=TEXTURE)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    with Image.open(args.texture) as image:
        texture = np.asarray(image.convert("RGB"), dtype=np.float32)
    args.out.mkdir(parents=True, exist_ok=True)
    frames = []
    for index in range(10):
        left = _render(texture, index, 0.0, CX, CY)
        right = _render(
            texture, index, -BASELINE_M, CX + RIGHT_OFFSET_PX[0], CY + RIGHT_OFFSET_PX[1]
        )
        (args.out / f"left_{index:03d}.jpg").write_bytes(_jpeg(left))
        (args.out / f"right_{index:03d}.jpg").write_bytes(_jpeg(right))
        normal, axis_depth, _ = _plane(index)
        frames.append(
            {
                "index": index,
                "left": f"left_{index:03d}.jpg",
                "right": f"right_{index:03d}.jpg",
                # The plane in the left camera frame: points p with normal . p == offset_m.
                "plane_normal": [round(float(c), 9) for c in normal],
                "plane_offset_m": round(float(normal[2]) * axis_depth, 9),
            }
        )
    calibration = {
        "source": "scripts/render_plane_stereo_fixture.py over Poly Haven rocks_ground_02 (CC0-1.0)",
        "image_width": WIDTH,
        "image_height": HEIGHT,
        "fx": FX,
        "fy": FY,
        "cx": CX,
        "cy": CY,
        "right_cx": CX + RIGHT_OFFSET_PX[0],
        "right_cy": CY + RIGHT_OFFSET_PX[1],
        "baseline_m": BASELINE_M,
        "frames": frames,
    }
    text = json.dumps(calibration, indent=1) + "\n"
    (args.out / "calibration.json").write_text(text, encoding="utf-8")
    print(f"{len(frames)} pairs in {args.out}")


if __name__ == "__main__":
    main()
