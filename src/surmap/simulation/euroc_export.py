"""Write a EuRoC-style session from SurMap stereo + GPS contracts."""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from surmap.euroc import stationary_imu_csv
from surmap.simulation.calibration import StereoCalibrationSpec, render_cam_sensor_yaml
from surmap.types import GpsCheckpoint, StereoFramePair


@dataclass(frozen=True)
class ExportResult:
    root: Path
    pair_count: int
    gps_count: int


def export_euroc_session(
    output_dir: Path,
    frames: Sequence[StereoFramePair],
    calibration: StereoCalibrationSpec,
    gps: Sequence[GpsCheckpoint] = (),
) -> ExportResult:
    """Stage stereo pairs + calibration (+ optional GPS) as EuRoC `mav0/`."""
    if not frames:
        raise ValueError("cannot export an empty frame list")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    mav0 = root / "mav0"

    for channel in (0, 1):
        cam_dir = mav0 / f"cam{channel}"
        (cam_dir / "data").mkdir(parents=True, exist_ok=True)
        (cam_dir / "sensor.yaml").write_text(
            render_cam_sensor_yaml(calibration, channel),
            encoding="utf-8",
        )

    for frame in frames:
        _write_channel(mav0, frame, channel=0, ref=frame.left_ref, data=frame.left_data)
        _write_channel(mav0, frame, channel=1, ref=frame.right_ref, data=frame.right_data)

    imu_dir = mav0 / "imu0"
    imu_dir.mkdir(parents=True, exist_ok=True)
    (imu_dir / "sensor.yaml").write_text("sensor_type: imu\n", encoding="utf-8")
    (imu_dir / "data.csv").write_text(stationary_imu_csv(frames), encoding="utf-8")

    if gps:
        gps_dir = mav0 / "gps0"
        gps_dir.mkdir(parents=True, exist_ok=True)
        with (gps_dir / "data.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["t_ns", "lat", "lon", "alt", "accuracy_m"],
            )
            writer.writeheader()
            for fix in gps:
                writer.writerow(
                    {
                        "t_ns": fix.t_ns,
                        "lat": fix.lat,
                        "lon": fix.lon,
                        "alt": fix.alt,
                        "accuracy_m": fix.accuracy_m,
                    }
                )

    return ExportResult(root=root, pair_count=len(frames), gps_count=len(gps))


def _write_channel(
    mav0: Path,
    frame: StereoFramePair,
    *,
    channel: int,
    ref: str,
    data: bytes,
) -> None:
    target = mav0 / f"cam{channel}" / "data" / f"{frame.t_ns}.png"
    if data:
        with Image.open(io.BytesIO(data)) as image:
            image.convert("L").save(target, format="PNG")
        return
    source = Path(ref)
    if not source.is_file():
        raise FileNotFoundError(
            f"frame {frame.frame_id} channel {channel}: ref {ref!r} is not a file"
        )
    with Image.open(source) as image:
        image.convert("L").save(target, format="PNG")
