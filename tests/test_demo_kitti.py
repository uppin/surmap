"""KITTI raw demo scene: conversion to the EuRoC layout and per-dataset tuning."""

import hashlib
import io
import threading
import urllib.request
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from surmap.demo.datasets import (
    DATASETS,
    DatasetSpec,
    DemoCalibration,
    PreparedDataset,
    ZipAsset,
    ensure_dataset,
    load_calibration,
)
from surmap.demo.server import DemoPlayer, depth_colour, make_demo_server, stream_backend_options

DRIVE = "2011_09_26/2011_09_26_drive_0009_sync"
P_RECT_00 = "7.215377e+02 0 6.095593e+02 0 0 7.215377e+02 1.728540e+02 0 0 0 1 0"
P_RECT_01 = "7.215377e+02 0 6.095593e+02 -3.875744e+02 0 7.215377e+02 1.728540e+02 0 0 0 1 0"
CALIB_CAM_TO_CAM = (
    "calib_time: 09-Jan-2012 13:57:47\n"
    "S_rect_00: 1.242000e+03 3.750000e+02\n"
    f"P_rect_00: {P_RECT_00}\n"
    "S_rect_01: 1.242000e+03 3.750000e+02\n"
    f"P_rect_01: {P_RECT_01}\n"
)
FIRST_T_NS = 1_317_042_164_329_372_928  # 2011-09-26 13:02:44.329372928
SECOND_T_NS = 1_317_042_164_433_055_488  # 2011-09-26 13:02:44.433055488


def _png(shade: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (1242, 375), shade).save(buffer, format="PNG")
    return buffer.getvalue()


def _drive_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for camera, stamps in (
            ("image_00", ("13:02:44.329372928", "13:02:44.433055488")),
            ("image_01", ("13:02:44.329373184", "13:02:44.433055744")),
        ):
            for index in (0, 1):
                shade = 10 * index + (1 if camera == "image_01" else 0)
                archive.writestr(f"{DRIVE}/{camera}/data/{index:010d}.png", _png(shade))
            archive.writestr(
                f"{DRIVE}/{camera}/timestamps.txt",
                "".join(f"2011-09-26 {stamp}\n" for stamp in stamps),
            )
        archive.writestr(f"{DRIVE}/velodyne_points/data/0000000000.bin", b"\x00" * 64)


def _calib_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("2011_09_26/calib_cam_to_cam.txt", CALIB_CAM_TO_CAM)


def _asset(path: Path, url: str) -> ZipAsset:
    data = path.read_bytes()
    return ZipAsset(url=url, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def a_kitti_drive(tmp_path: Path) -> tuple[DatasetSpec, dict[str, Path]]:
    """A two-frame KITTI raw drive and its calibration, as the registry would pin them."""
    drive, calib = tmp_path / "drive.zip", tmp_path / "calib.zip"
    _drive_zip(drive)
    _calib_zip(calib)
    drive_asset = _asset(drive, "https://example.invalid/drive.zip")
    spec = DatasetSpec(
        dataset_id="kitti-tiny",
        title="KITTI tiny",
        description="two city frames",
        zip_url=drive_asset.url,
        zip_size_bytes=drive_asset.size_bytes,
        zip_sha256=drive_asset.sha256,
        official_url="https://www.cvlibs.net/datasets/kitti/raw_data.php",
        dataset_format="kitti-raw",
        calibration=_asset(calib, "https://example.invalid/calib.zip"),
        display_size=(620, 188),
        fps=10.0,
        depth_stops_m=(5.0, 15.0, 40.0),
        max_map_depth_m=30.0,
        credit="KITTI (Geiger et al.), CC BY-NC-SA 3.0",
    )
    return spec, {drive_asset.url: drive, "https://example.invalid/calib.zip": calib}


def prepare(spec: DatasetSpec, sources: dict[str, Path], cache: Path) -> PreparedDataset:
    def fetch(url: str, target: Path) -> None:
        target.write_bytes(sources[url].read_bytes())

    return ensure_dataset(spec, cache, log=lambda _: None, fetch=fetch)


def test_a_kitti_drive_prepares_into_stereo_pairs_named_by_cam0_time(tmp_path: Path) -> None:
    # Given a KITTI raw drive whose two cameras stamp each pair microseconds apart
    spec, sources = a_kitti_drive(tmp_path)

    # When it is prepared
    prepared = prepare(spec, sources, tmp_path / "cache")

    # Then each pair is named by cam0's timestamp and holds that index's images
    assert prepared.timestamps_ns == (FIRST_T_NS, SECOND_T_NS)
    assert prepared.frame_path(0, SECOND_T_NS).read_bytes() == _png(10)
    assert prepared.frame_path(1, SECOND_T_NS).read_bytes() == _png(11)


def test_a_kitti_drive_keeps_only_the_grey_stereo_pair(tmp_path: Path) -> None:
    # Given a drive that also carries LiDAR scans
    spec, sources = a_kitti_drive(tmp_path)

    # When it is prepared
    prepared = prepare(spec, sources, tmp_path / "cache")

    # Then nothing but the two grey cameras was extracted
    extracted = {path.parent.parent.name for path in prepared.root.rglob("*.png")}
    assert extracted == {"cam0", "cam1"}
    assert not list(prepared.root.rglob("*.bin"))


def test_kitti_rectified_calibration_becomes_the_stereo_calibration(tmp_path: Path) -> None:
    # Given a drive whose rectified projections put cam1 0.537 m to the right
    spec, sources = a_kitti_drive(tmp_path)

    # When it is prepared and its calibration loaded
    calibration = load_calibration(prepare(spec, sources, tmp_path / "cache"))

    # Then intrinsics come from P_rect_00, size from S_rect_00, baseline from P_rect_01
    assert calibration == DemoCalibration(
        fx=721.5377,
        fy=721.5377,
        cx=609.5593,
        cy=172.854,
        baseline_m=387.5744 / 721.5377,
        width=1242,
        height=375,
    )


def test_kitti_frames_are_already_rectified_so_carry_no_distortion(tmp_path: Path) -> None:
    # Given / When a drive is prepared
    spec, sources = a_kitti_drive(tmp_path)
    prepared = prepare(spec, sources, tmp_path / "cache")

    # Then both cameras' sensor.yaml declare zero distortion
    for camera in ("cam0", "cam1"):
        assert "distortion_coefficients: [0.0, 0.0, 0.0, 0.0]" in prepared.sensor_yaml(camera)


def test_a_tampered_calibration_zip_is_refused(tmp_path: Path) -> None:
    # Given a calibration zip that does not match its pinned hash
    spec, sources = a_kitti_drive(tmp_path)
    assert spec.calibration is not None
    tampered = replace(spec, calibration=replace(spec.calibration, sha256="0" * 64))

    # When / Then preparing it fails
    with pytest.raises(ValueError, match="SHA-256"):
        prepare(tampered, sources, tmp_path / "cache")


def test_the_registry_offers_an_outdoor_kitti_city_drive() -> None:
    # Given / When the KITTI entry is read
    spec = DATASETS["kitti-2011-09-26-drive-0009"]

    # Then it is fetched from KITTI's own host, tuned for a street, and credited
    assert spec.dataset_format == "kitti-raw"
    assert spec.zip_url.startswith("https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/")
    assert spec.calibration is not None
    assert spec.calibration.url.endswith("/2011_09_26_calib.zip")
    assert (spec.display_size, spec.fps) == ((620, 188), 10.0)
    assert spec.depth_stops_m == (5.0, 15.0, 40.0)
    assert spec.max_map_depth_m == 30.0
    assert "KITTI" in spec.credit and "CC BY-NC-SA 3.0" in spec.credit


def test_euroc_keeps_its_indoor_tuning() -> None:
    # Given / When the EuRoC entry is read
    spec = DATASETS["euroc-v1-01-easy"]

    # Then its size, rate and depth tuning are what the demo always used
    assert (spec.display_size, spec.fps) == ((376, 240), 20.0)
    assert spec.depth_stops_m == (1.0, 3.0, 6.0)
    assert spec.max_map_depth_m == 6.0


def test_frames_play_at_the_datasets_display_size(tmp_path: Path) -> None:
    # Given a prepared KITTI drive
    spec, sources = a_kitti_drive(tmp_path)
    player = DemoPlayer(prepare(spec, sources, tmp_path / "cache"), with_rtabmap=False)

    # When the first frame is played
    frame = next(event for event in player.events() if event.kind == "frame")

    # Then its image is the dataset's display size
    with Image.open(io.BytesIO(frame.jpeg)) as image:
        assert image.size == (620, 188)


def test_the_sidecar_is_configured_at_display_size_with_the_datasets_depth_cap(
    tmp_path: Path,
) -> None:
    # Given a prepared KITTI drive
    spec, sources = a_kitti_drive(tmp_path)
    prepared = prepare(spec, sources, tmp_path / "cache")

    # When the live backend's options are derived
    options = stream_backend_options(prepared)

    # Then frames, calibration and depth cap all follow the dataset
    assert (options.width, options.height, options.max_depth_m) == (620, 188, 30.0)
    assert "resolution: [620, 188]" in options.cam0_yaml
    assert "resolution: [620, 188]" in options.cam1_yaml


def test_playback_defaults_to_the_datasets_rate(tmp_path: Path) -> None:
    # Given a 10 Hz KITTI drive
    spec, sources = a_kitti_drive(tmp_path)
    prepared = prepare(spec, sources, tmp_path / "cache")

    # When / Then the player paces at 10 fps unless told otherwise
    assert DemoPlayer(prepared, with_rtabmap=False).fps == 10.0
    assert DemoPlayer(prepared, fps=5.0, with_rtabmap=False).fps == 5.0


def test_batch_mapping_is_refused_for_a_drive_without_an_imu(tmp_path: Path) -> None:
    # Given a KITTI drive, which carries no IMU in the EuRoC layout
    spec, sources = a_kitti_drive(tmp_path)
    prepared = prepare(spec, sources, tmp_path / "cache")

    # When / Then the batch sidecar, which needs one, is refused up front
    with pytest.raises(ValueError, match="IMU"):
        DemoPlayer(prepared, rtabmap_mode="batch")


def test_depth_colours_follow_the_datasets_stops() -> None:
    # Given / When / Then street stops put 15 m at the mid colour and 40 m at far
    stops = (5.0, 15.0, 40.0)
    assert depth_colour(5.0, stops) == "#ff5a3c"
    assert depth_colour(15.0, stops) == "#ffb03a"
    assert depth_colour(40.0, stops) == "#2fd4c4"


def test_the_page_credits_the_dataset_and_sizes_the_view_to_it(tmp_path: Path) -> None:
    # Given a demo server for a prepared KITTI drive
    spec, sources = a_kitti_drive(tmp_path)
    server = make_demo_server(
        prepare(spec, sources, tmp_path / "cache"), host="127.0.0.1", port=0, with_rtabmap=False
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # When the page is fetched
        host, port = str(server.server_address[0]), int(server.server_address[1])
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
            page = response.read().decode()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    # Then it credits KITTI, sizes the view to 620x188 and labels the street stops
    assert "KITTI (Geiger et al.), CC BY-NC-SA 3.0" in page
    assert 'width="620" height="188"' in page
    assert "≤5 m" in page and "≥40 m" in page
