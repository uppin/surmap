"""Load a filesystem SITL capture dump (no ROS2 dependency).

Capture layout (operator fills this from Gazebo/PX4 topics or bags)::

    capture/
      calibration.json   # StereoCalibrationSpec fields
      frames.jsonl       # one JSON object per line: frame_id, t_ns, left, right
      gps.csv            # optional: t_ns,lat,lon,alt,accuracy_m
      images/…           # paths referenced by frames.jsonl
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from surmap.simulation.calibration import StereoCalibrationSpec
from surmap.types import GpsCheckpoint, StereoFramePair

_REQUIRED_CAL = (
    "calibration_id",
    "width",
    "height",
    "fx",
    "fy",
    "cx",
    "cy",
    "baseline_m",
)


def load_sitl_capture(
    capture_dir: Path,
) -> tuple[list[StereoFramePair], StereoCalibrationSpec, list[GpsCheckpoint]]:
    """Parse a capture directory into SurMap contracts."""
    root = Path(capture_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"SITL capture directory not found: {root}")

    cal_path = root / "calibration.json"
    raw = json.loads(cal_path.read_text(encoding="utf-8"))
    missing = [key for key in _REQUIRED_CAL if key not in raw]
    if missing:
        raise ValueError(f"calibration.json missing fields: {', '.join(missing)}")
    calibration = StereoCalibrationSpec(
        calibration_id=str(raw["calibration_id"]),
        width=int(raw["width"]),
        height=int(raw["height"]),
        fx=float(raw["fx"]),
        fy=float(raw["fy"]),
        cx=float(raw["cx"]),
        cy=float(raw["cy"]),
        baseline_m=float(raw["baseline_m"]),
        rate_hz=float(raw.get("rate_hz", 20.0)),
    )

    frames_path = root / "frames.jsonl"
    frames: list[StereoFramePair] = []
    for line_no, line in enumerate(frames_path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        row = json.loads(text)
        try:
            frame_id = int(row["frame_id"])
            t_ns = int(row["t_ns"])
            left_rel = str(row["left"])
            right_rel = str(row["right"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"frames.jsonl line {line_no} is invalid: {exc}") from exc
        left = (root / left_rel).resolve()
        right = (root / right_rel).resolve()
        if not left.is_file() or not right.is_file():
            raise FileNotFoundError(
                f"frames.jsonl line {line_no}: missing image(s) {left_rel!r} / {right_rel!r}"
            )
        frames.append(
            StereoFramePair(
                frame_id=frame_id,
                t_ns=t_ns,
                left_ref=str(left),
                right_ref=str(right),
                calibration_id=calibration.calibration_id,
            )
        )
    if not frames:
        raise ValueError("frames.jsonl has no frame rows")

    gps: list[GpsCheckpoint] = []
    gps_path = root / "gps.csv"
    if gps_path.is_file():
        with gps_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                gps.append(
                    GpsCheckpoint(
                        t_ns=int(row["t_ns"]),
                        lat=float(row["lat"]),
                        lon=float(row["lon"]),
                        alt=float(row["alt"]),
                        accuracy_m=float(row["accuracy_m"]),
                    )
                )
    return frames, calibration, gps
