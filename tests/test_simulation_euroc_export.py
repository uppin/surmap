"""Machine 3: SITL capture directory → EuRoC session SurMap already understands."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest
from PIL import Image

from surmap.simulation.calibration import StereoCalibrationSpec, render_cam_sensor_yaml
from surmap.simulation.euroc_export import export_euroc_session
from surmap.simulation.sitl_capture import load_sitl_capture

FIXTURE = Path(__file__).parent / "fixtures" / "sitl_capture_tiny"


def _translation(sensor_yaml: str) -> tuple[float, float, float]:
    """Body-frame camera origin from an EuRoC `T_BS` data row."""
    match = re.search(r"data: \[([^\]]+)\]", sensor_yaml)
    assert match is not None
    values = [float(part) for part in match.group(1).split(",")]
    return values[3], values[7], values[11]


def _write_tiny_capture(root: Path) -> Path:
    """A two-pair SITL capture directory with GPS (operator dump shape)."""
    images = root / "images"
    images.mkdir(parents=True)
    for index in range(2):
        for side, colour in (("left", 40), ("right", 80)):
            path = images / f"{side}_{index:03d}.png"
            Image.new("L", (64, 48), colour).save(path, format="PNG")
    (root / "calibration.json").write_text(
        json.dumps(
            {
                "calibration_id": "gazebo-stereo-v1",
                "width": 64,
                "height": 48,
                "fx": 50.0,
                "fy": 50.0,
                "cx": 32.0,
                "cy": 24.0,
                "baseline_m": 0.12,
                "rate_hz": 20.0,
            }
        ),
        encoding="utf-8",
    )
    frames = [
        {
            "frame_id": 0,
            "t_ns": 1_000_000_000,
            "left": "images/left_000.png",
            "right": "images/right_000.png",
        },
        {
            "frame_id": 1,
            "t_ns": 1_050_000_000,
            "left": "images/left_001.png",
            "right": "images/right_001.png",
        },
    ]
    (root / "frames.jsonl").write_text(
        "\n".join(json.dumps(row) for row in frames) + "\n",
        encoding="utf-8",
    )
    with (root / "gps.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["t_ns", "lat", "lon", "alt", "accuracy_m"])
        writer.writerow([1_000_000_000, 47.3769, 8.5417, 410.0, 1.5])
        writer.writerow([1_050_000_000, 47.3770, 8.5418, 411.0, 1.5])
    return root


def test_exporting_a_sitl_capture_writes_matching_euroc_stereo_pairs(
    tmp_path: Path,
) -> None:
    # Given a Gazebo/PX4-style capture directory with two stereo pairs
    capture = _write_tiny_capture(tmp_path / "capture")
    frames, calibration, gps = load_sitl_capture(capture)

    # When it is exported to a SurMap EuRoC session
    result = export_euroc_session(tmp_path / "session", frames, calibration, gps)

    # Then L/R PNGs share t_ns names under mav0/cam{0,1}/data
    cam0 = result.root / "mav0" / "cam0" / "data"
    cam1 = result.root / "mav0" / "cam1" / "data"
    assert sorted(p.name for p in cam0.glob("*.png")) == [
        "1000000000.png",
        "1050000000.png",
    ]
    assert sorted(p.name for p in cam1.glob("*.png")) == [
        "1000000000.png",
        "1050000000.png",
    ]
    assert result.pair_count == 2
    with Image.open(cam0 / "1000000000.png") as image:
        assert image.size == (64, 48)


def test_left_eye_is_on_negative_euroc_body_y() -> None:
    # Given a 0.12 m rig, the same baseline the demo fixture uses
    spec = StereoCalibrationSpec(
        calibration_id="gazebo-stereo-v1",
        width=64,
        height=48,
        fx=50.0,
        fy=50.0,
        cx=32.0,
        cy=24.0,
        baseline_m=0.12,
    )

    # When each eye's extrinsics are rendered
    cam0 = render_cam_sensor_yaml(spec, 0)
    cam1 = render_cam_sensor_yaml(spec, 1)

    # Then the left eye is at −Y and the right eye at +Y (EuRoC +Y is right)
    assert _translation(cam0) == pytest.approx((0.0, -0.06, 0.0))
    assert _translation(cam1) == pytest.approx((0.0, 0.06, 0.0))


def test_exported_sensor_yaml_carries_intrinsics_resolution_and_baseline(
    tmp_path: Path,
) -> None:
    # Given the same capture
    capture = _write_tiny_capture(tmp_path / "capture")
    frames, calibration, gps = load_sitl_capture(capture)

    # When exported
    result = export_euroc_session(tmp_path / "session", frames, calibration, gps)

    # Then cam0/cam1 sensor.yaml match SurMap's EuRoC expectations
    cam0_yaml = (result.root / "mav0" / "cam0" / "sensor.yaml").read_text(encoding="utf-8")
    cam1_yaml = (result.root / "mav0" / "cam1" / "sensor.yaml").read_text(encoding="utf-8")
    assert "resolution: [64, 48]" in cam0_yaml
    assert "intrinsics: [50.0, 50.0, 32.0, 24.0]" in cam0_yaml
    assert "sensor_type: camera" in cam0_yaml
    # EuRoC body +Y is right, so the left eye (cam0) is at −baseline/2.
    assert _translation(cam0_yaml)[1] == pytest.approx(-0.06)
    assert _translation(cam1_yaml)[1] == pytest.approx(0.06)
    assert (result.root / "mav0" / "imu0" / "sensor.yaml").is_file()
    assert (result.root / "mav0" / "imu0" / "data.csv").is_file()


def test_exported_session_includes_gps_checkpoints(tmp_path: Path) -> None:
    # Given a capture with two GPS rows
    capture = _write_tiny_capture(tmp_path / "capture")
    frames, calibration, gps = load_sitl_capture(capture)

    # When exported
    result = export_euroc_session(tmp_path / "session", frames, calibration, gps)

    # Then gps0/data.csv holds the same checkpoints (SurMap GpsCheckpoint shape)
    gps_path = result.root / "mav0" / "gps0" / "data.csv"
    assert gps_path.is_file()
    rows = list(csv.DictReader(gps_path.open(encoding="utf-8")))
    assert len(rows) == 2
    assert rows[0]["t_ns"] == "1000000000"
    assert float(rows[0]["lat"]) == 47.3769
    assert float(rows[1]["lon"]) == 8.5418
    assert result.gps_count == 2


def test_checked_in_sitl_fixture_loads_without_gazebo() -> None:
    # Given the tiny fixture committed for CI (no Gazebo / ROS2 in the loop)
    frames, calibration, gps = load_sitl_capture(FIXTURE)

    # Then it is a valid two-pair capture SurMap can export
    assert len(frames) == 2
    assert frames[0].t_ns == frames[1].t_ns - 50_000_000
    assert calibration.calibration_id == "gazebo-stereo-v1"
    assert calibration.baseline_m == 0.12
    assert len(gps) == 2


def test_exported_session_is_readable_by_demo_calibration_loader(
    tmp_path: Path,
) -> None:
    # Given a SITL capture exported to EuRoC (Machine 3 → SurMap contract)
    from surmap.demo.datasets import DatasetSpec, PreparedDataset, load_calibration

    frames, calibration, gps = load_sitl_capture(FIXTURE)
    result = export_euroc_session(tmp_path / "session", frames, calibration, gps)
    prepared = PreparedDataset(
        spec=DatasetSpec(
            dataset_id="sitl-tiny",
            title="SITL tiny",
            description="fixture export",
            zip_url="https://example.invalid/sitl.zip",
            zip_size_bytes=1,
            zip_sha256="0" * 64,
            official_url="https://example.invalid/",
        ),
        root=result.root,
        timestamps_ns=tuple(frame.t_ns for frame in frames),
    )

    # When the demo calibration loader reads mav0 sensor.yaml
    demo_cal = load_calibration(prepared)

    # Then baseline and intrinsics match the capture (no sim-only fork)
    assert demo_cal.width == 64
    assert demo_cal.height == 48
    assert demo_cal.fx == 50.0
    assert demo_cal.baseline_m == pytest.approx(0.12, abs=1e-9)
