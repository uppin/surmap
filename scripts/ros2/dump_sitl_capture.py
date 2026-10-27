#!/usr/bin/env python3
"""Dump ROS2 stereo + GPS topics into a SurMap SITL capture directory.

Run with ROS 2 Jazzy sourced (not the SurMap uv venv alone)::

    source /opt/ros/jazzy/setup.bash
    python3 scripts/ros2/dump_sitl_capture.py \\
      --left /cam_left/image_raw --right /cam_right/image_raw \\
      --gps /mavros/global_position/global \\
      --output ~/sitl-runs/hover-01 \\
      --seconds 15

This script never publishes flight commands. It only subscribes.
Image bytes are decoded with Pillow (no cv_bridge / NumPy pin fight).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, help="Left Image topic")
    parser.add_argument("--right", required=True, help="Right Image topic")
    parser.add_argument(
        "--left-info",
        default="",
        help="Optional left CameraInfo (fills fx/fy/cx/cy/width/height)",
    )
    parser.add_argument("--gps", default="", help="Optional NavSatFix topic")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--baseline-m", type=float, default=0.07)
    parser.add_argument("--calibration-id", default="gazebo-surmap-stereo-v1")
    parser.add_argument("--pair-slop-ns", type=int, default=20_000_000)
    return parser


def _require_ros() -> None:
    try:
        import rclpy  # noqa: F401
        from sensor_msgs.msg import Image, NavSatFix  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "ROS 2 Python packages missing. Source Jazzy first:\n"
            "  source /opt/ros/jazzy/setup.bash\n"
            f"Import error: {exc}"
        ) from exc


def _image_msg_to_png(msg: object, target: Path) -> None:
    """Write a sensor_msgs/Image to PNG without cv_bridge."""
    from PIL import Image as PilImage

    encoding = str(getattr(msg, "encoding", "")).lower()
    width = int(getattr(msg, "width"))
    height = int(getattr(msg, "height"))
    data = bytes(getattr(msg, "data"))
    if encoding in ("rgb8", "bgr8"):
        mode = "RGB"
        raw = data
        image = PilImage.frombytes(mode, (width, height), raw)
        if encoding == "bgr8":
            r, g, b = image.split()
            image = PilImage.merge("RGB", (b, g, r))
    elif encoding in ("mono8", "8uc1"):
        image = PilImage.frombytes("L", (width, height), data)
    else:
        raise ValueError(f"unsupported image encoding {encoding!r} (use rgb8/bgr8/mono8)")
    image.save(target, format="PNG")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _require_ros()

    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CameraInfo, Image, NavSatFix

    out = args.output
    images = out / "images"
    images.mkdir(parents=True, exist_ok=True)

    left_buf: dict[int, object] = {}
    right_buf: dict[int, object] = {}
    pairs: list[tuple[int, object, object]] = []
    gps_rows: list[list[float | int]] = []
    cam_info: dict[str, float | int] = {
        "width": 640,
        "height": 480,
        "fx": 381.36,
        "fy": 381.36,
        "cx": 320.0,
        "cy": 240.0,
    }

    class Dumper(Node):
        def __init__(self) -> None:
            super().__init__("surmap_sitl_capture_dumper")
            self.create_subscription(
                Image, args.left, self._on_left, qos_profile_sensor_data
            )
            self.create_subscription(
                Image, args.right, self._on_right, qos_profile_sensor_data
            )
            if args.left_info:
                self.create_subscription(
                    CameraInfo, args.left_info, self._on_info, qos_profile_sensor_data
                )
            if args.gps:
                self.create_subscription(
                    NavSatFix, args.gps, self._on_gps, qos_profile_sensor_data
                )

        def _stamp_ns(self, msg: Image) -> int:
            return int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)

        def _on_info(self, msg: CameraInfo) -> None:
            cam_info["width"] = int(msg.width)
            cam_info["height"] = int(msg.height)
            cam_info["fx"] = float(msg.k[0])
            cam_info["fy"] = float(msg.k[4])
            cam_info["cx"] = float(msg.k[2])
            cam_info["cy"] = float(msg.k[5])

        def _on_gps(self, msg: NavSatFix) -> None:
            t_ns = int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)
            acc = float(msg.position_covariance[0]) if msg.position_covariance else 1.0
            if not math.isfinite(acc) or acc <= 0.0:
                acc = 1.0
            gps_rows.append(
                [t_ns, float(msg.latitude), float(msg.longitude), float(msg.altitude), acc]
            )

        def _on_left(self, msg: Image) -> None:
            left_buf[self._stamp_ns(msg)] = msg
            self._try_pair()

        def _on_right(self, msg: Image) -> None:
            right_buf[self._stamp_ns(msg)] = msg
            self._try_pair()

        def _try_pair(self) -> None:
            if not left_buf or not right_buf:
                return
            for lt in list(left_buf):
                best_rt = min(right_buf, key=lambda rt: abs(rt - lt))
                if abs(best_rt - lt) > args.pair_slop_ns:
                    continue
                pairs.append((lt, left_buf.pop(lt), right_buf.pop(best_rt)))
                return

    rclpy.init()
    node = Dumper()
    end = time.monotonic() + args.seconds
    try:
        while time.monotonic() < end and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    if not pairs:
        print(
            "no stereo pairs captured — check topic names and that SITL is publishing",
            file=sys.stderr,
        )
        return 1

    frames_path = out / "frames.jsonl"
    with frames_path.open("w", encoding="utf-8") as frames_out:
        for frame_id, (t_ns, left_msg, right_msg) in enumerate(pairs):
            left_name = f"images/left_{frame_id:04d}.png"
            right_name = f"images/right_{frame_id:04d}.png"
            _image_msg_to_png(left_msg, out / left_name)
            _image_msg_to_png(right_msg, out / right_name)
            frames_out.write(
                json.dumps(
                    {
                        "frame_id": frame_id,
                        "t_ns": t_ns,
                        "left": left_name,
                        "right": right_name,
                    }
                )
                + "\n"
            )

    calibration = {
        "calibration_id": args.calibration_id,
        "width": int(cam_info["width"]),
        "height": int(cam_info["height"]),
        "fx": float(cam_info["fx"]),
        "fy": float(cam_info["fy"]),
        "cx": float(cam_info["cx"]),
        "cy": float(cam_info["cy"]),
        "baseline_m": args.baseline_m,
        "rate_hz": 20.0,
    }
    (out / "calibration.json").write_text(
        json.dumps(calibration, indent=2) + "\n", encoding="utf-8"
    )

    if gps_rows:
        with (out / "gps.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["t_ns", "lat", "lon", "alt", "accuracy_m"])
            writer.writerows(gps_rows)

    print(f"wrote {len(pairs)} pairs (+ {len(gps_rows)} GPS) → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
