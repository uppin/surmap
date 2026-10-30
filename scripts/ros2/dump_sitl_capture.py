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
    parser.add_argument(
        "--seg",
        default="",
        help="Ground-truth instance segmentation Image topic (optional)",
    )
    parser.add_argument(
        "--seg-class",
        default="",
        help="Ground-truth semantic segmentation Image topic (optional)",
    )
    parser.add_argument(
        "--pose",
        default="",
        help="Ground-truth camera PoseStamped topic (translation + quaternion)",
    )
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


def _load_sitl_dump() -> object:
    """Load SurMap's dumper helpers from this checkout, without an install."""
    import importlib

    repo_src = Path(__file__).resolve().parents[2] / "src"
    entry = str(repo_src)
    if repo_src.is_dir() and entry not in sys.path:
        sys.path.insert(0, entry)
    return importlib.import_module("surmap.simulation.sitl_dump")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _require_ros()
    sitl_dump = _load_sitl_dump()

    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CameraInfo, Image, NavSatFix

    out = args.output
    images = out / "images"
    images.mkdir(parents=True, exist_ok=True)

    left_buf: dict[int, object] = {}
    right_buf: dict[int, object] = {}
    seg_buf: dict[int, object] = {}
    class_buf: dict[int, object] = {}
    pose_buf: list[object] = []
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
            if args.seg:
                self.create_subscription(
                    Image, args.seg, self._on_seg, qos_profile_sensor_data
                )
            if args.seg_class:
                self.create_subscription(
                    Image, args.seg_class, self._on_class, qos_profile_sensor_data
                )
            if args.pose:
                from geometry_msgs.msg import PoseStamped

                self.create_subscription(
                    PoseStamped, args.pose, self._on_pose, qos_profile_sensor_data
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
            if msg.position_covariance:
                acc = sitl_dump.navsat_accuracy_m(float(msg.position_covariance[0]))
            else:
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

        def _on_seg(self, msg: Image) -> None:
            seg_buf[self._stamp_ns(msg)] = msg

        def _on_class(self, msg: Image) -> None:
            class_buf[self._stamp_ns(msg)] = msg

        def _on_pose(self, msg: object) -> None:
            header = getattr(msg, "header")
            pose = getattr(msg, "pose")
            stamp = header.stamp
            t_ns = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
            position = pose.position
            quat = pose.orientation
            frame = str(header.frame_id) or "gazebo_enu"
            pose_buf.append(
                sitl_dump.StampedPose(
                    t_ns,
                    float(position.x),
                    float(position.y),
                    float(position.z),
                    (float(quat.x), float(quat.y), float(quat.z), float(quat.w)),
                    frame=frame,
                )
            )

        def _try_pair(self) -> None:
            pair = sitl_dump.take_stereo_pair(left_buf, right_buf, slop_ns=args.pair_slop_ns)
            if pair is not None:
                pairs.append(pair)

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
    seg_hits = 0
    pose_hits = 0
    pose_lines: list[str] = []
    with frames_path.open("w", encoding="utf-8") as frames_out:
        for frame_id, (t_ns, left_msg, right_msg) in enumerate(pairs):
            left_name = f"images/left_{frame_id:04d}.png"
            right_name = f"images/right_{frame_id:04d}.png"
            sitl_dump.image_msg_to_png(left_msg, out / left_name)
            sitl_dump.image_msg_to_png(right_msg, out / right_name)
            record: dict[str, object] = {
                "frame_id": frame_id,
                "t_ns": t_ns,
                "clock": "sim_time",
                "left": left_name,
                "right": right_name,
            }
            seg_stamp = sitl_dump.nearest_stamp(tuple(seg_buf), t_ns, slop_ns=args.pair_slop_ns)
            if seg_stamp is not None:
                seg_name = f"images/seg_{frame_id:04d}.png"
                sitl_dump.label_image_to_png(seg_buf[seg_stamp], out / seg_name)
                record["seg"] = seg_name
                seg_hits += 1
            class_stamp = sitl_dump.nearest_stamp(
                tuple(class_buf), t_ns, slop_ns=args.pair_slop_ns
            )
            if class_stamp is not None:
                class_name = f"images/class_{frame_id:04d}.png"
                sitl_dump.label_image_to_png(class_buf[class_stamp], out / class_name)
                record["seg_class"] = class_name
            pose = sitl_dump.nearest_pose(pose_buf, t_ns, slop_ns=args.pair_slop_ns)
            if pose is not None:
                record["pose"] = sitl_dump.pose_record(pose)
                pose_lines.append(json.dumps(sitl_dump.pose_record(pose)))
                pose_hits += 1
            frames_out.write(json.dumps(record) + "\n")

    if args.seg and seg_hits == 0:
        print("no segmentation image matched a stereo pair", file=sys.stderr)
        return 1
    if args.pose and pose_hits == 0:
        print("no ground-truth pose matched a stereo pair", file=sys.stderr)
        return 1
    if pose_lines:
        (out / "poses.jsonl").write_text("\n".join(pose_lines) + "\n", encoding="utf-8")

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

    print(
        f"wrote {len(pairs)} pairs (+ {len(gps_rows)} GPS, "
        f"{seg_hits} seg, {pose_hits} poses) → {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
