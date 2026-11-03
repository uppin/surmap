"""KITTI colour variant and GPS (oxts) extraction into the EuRoC layout."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from surmap.demo.datasets import DATASETS, DatasetSpec, ZipAsset, ensure_dataset

DRIVE = "2011_09_26/2011_09_26_drive_0009_sync"
P = "7.215377e+02 0 6.095593e+02 {tx} 0 7.215377e+02 1.728540e+02 0 0 0 1 0"
CALIB = (
    "S_rect_00: 1.242000e+03 3.750000e+02\n"
    f"P_rect_00: {P.format(tx=0)}\n"
    "S_rect_01: 1.242000e+03 3.750000e+02\n"
    f"P_rect_01: {P.format(tx=-3.875744e02)}\n"
    "S_rect_02: 1.242000e+03 3.750000e+02\n"
    f"P_rect_02: {P.format(tx=0)}\n"
    "S_rect_03: 1.242000e+03 3.750000e+02\n"
    f"P_rect_03: {P.format(tx=-3.875744e02)}\n"
)
STAMPS = ("13:02:44.329372928", "13:02:44.433055488")
FIRST_T_NS = 1_317_042_164_329_372_928


def _png(mode: str, pixel: object) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (1242, 375), pixel).save(buffer, format="PNG")  # type: ignore[arg-type]
    return buffer.getvalue()


def _write(archive: zipfile.ZipFile, name: str, data: bytes | str) -> None:
    """One zip entry at a fixed date, so two builds of a fixture are byte-identical."""
    info = zipfile.ZipInfo(name, date_time=(2011, 9, 26, 0, 0, 0))
    archive.writestr(info, data)


def _drive_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for camera, mode, pixel in (
            ("image_00", "L", 10),
            ("image_01", "L", 11),
            ("image_02", "RGB", (200, 30, 30)),
            ("image_03", "RGB", (30, 30, 200)),
        ):
            for index in (0, 1):
                _write(archive, f"{DRIVE}/{camera}/data/{index:010d}.png", _png(mode, pixel))
            _write(
                archive,
                f"{DRIVE}/{camera}/timestamps.txt",
                "".join(f"2011-09-26 {stamp}\n" for stamp in STAMPS),
            )
        for index, (lat, lon) in enumerate(((49.01, 8.42), (49.02, 8.43))):
            _write(
                archive,
                f"{DRIVE}/oxts/data/{index:010d}.txt",
                f"{lat} {lon} 112.0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n",
            )
        _write(
            archive, f"{DRIVE}/oxts/timestamps.txt", "".join(f"2011-09-26 {s}\n" for s in STAMPS)
        )


def _spec(tmp_path: Path, dataset_id: str) -> tuple[DatasetSpec, dict[str, Path]]:
    drive, calib = tmp_path / f"{dataset_id}.zip", tmp_path / "calib.zip"
    _drive_zip(drive)
    with zipfile.ZipFile(calib, "w") as archive:
        _write(archive, "2011_09_26/calib_cam_to_cam.txt", CALIB)

    def asset(path: Path, url: str) -> ZipAsset:
        data = path.read_bytes()
        return ZipAsset(url=url, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    base = DATASETS[dataset_id]
    drive_asset = asset(drive, "https://example.invalid/drive.zip")
    spec = replace(
        base,
        zip_url=drive_asset.url,
        zip_size_bytes=drive_asset.size_bytes,
        zip_sha256=drive_asset.sha256,
        calibration=asset(calib, "https://example.invalid/calib.zip"),
    )
    return spec, {drive_asset.url: drive, "https://example.invalid/calib.zip": calib}


def _prepare(spec: DatasetSpec, sources: dict[str, Path], cache: Path):  # type: ignore[no-untyped-def]
    def fetch(url: str, target: Path) -> None:
        target.write_bytes(sources[url].read_bytes())

    return ensure_dataset(spec, cache, log=lambda _: None, fetch=fetch)


def test_the_color_variant_extracts_the_color_pair_in_color(tmp_path: Path) -> None:
    # Given the registered color variant of the drive
    spec, sources = _spec(tmp_path, "kitti-2011-09-26-drive-0009-color")

    # When it is prepared
    prepared = _prepare(spec, sources, tmp_path / "cache")

    # Then cam0/cam1 hold the color cameras' frames, still in color
    with Image.open(prepared.frame_path(0, FIRST_T_NS)) as frame:
        assert frame.mode == "RGB"
        assert frame.getpixel((2, 2)) == (200, 30, 30)


def test_the_grey_variant_still_extracts_only_the_grey_pair(tmp_path: Path) -> None:
    # Given the registered grey variant
    spec, sources = _spec(tmp_path, "kitti-2011-09-26-drive-0009")

    # When it is prepared
    prepared = _prepare(spec, sources, tmp_path / "cache")

    # Then its frames are the grey pair
    with Image.open(prepared.frame_path(0, FIRST_T_NS)) as frame:
        assert frame.mode == "L"


def test_oxts_positions_become_the_datasets_gps_track(tmp_path: Path) -> None:
    # Given a drive carrying oxts GPS fixes
    spec, sources = _spec(tmp_path, "kitti-2011-09-26-drive-0009")

    # When it is prepared
    prepared = _prepare(spec, sources, tmp_path / "cache")

    # Then the track is available as (lon, lat) points for the map preview
    track = prepared.gps_track()
    assert [(point.lon, point.lat) for point in track] == [(8.42, 49.01), (8.43, 49.02)]


def test_color_and_grey_download_the_shared_zip_once(tmp_path: Path) -> None:
    # Given both variants prepared into one cache with a counting fetch
    grey, sources = _spec(tmp_path, "kitti-2011-09-26-drive-0009")
    color, _ = _spec(tmp_path, "kitti-2011-09-26-drive-0009-color")
    # Both variants pin the same upstream zip; reuse the grey pin for the fetch.
    color = replace(
        color,
        zip_sha256=grey.zip_sha256,
        zip_size_bytes=grey.zip_size_bytes,
        calibration=grey.calibration,
    )
    fetched: list[str] = []

    def fetch(url: str, target: Path) -> None:
        fetched.append(url)
        target.write_bytes(sources[url].read_bytes())

    # When both are prepared
    ensure_dataset(grey, tmp_path / "cache", log=lambda _: None, fetch=fetch)
    ensure_dataset(color, tmp_path / "cache", log=lambda _: None, fetch=fetch)

    # Then the large drive zip was fetched once, not once per modality
    assert fetched.count("https://example.invalid/drive.zip") == 1


@pytest.mark.parametrize(
    "dataset_id", ["kitti-2011-09-26-drive-0009", "kitti-2011-09-26-drive-0009-color"]
)
def test_each_variant_plays_at_display_size(tmp_path: Path, dataset_id: str) -> None:
    # Given a prepared variant
    from surmap.demo.server import DemoPlayer

    spec, sources = _spec(tmp_path, dataset_id)
    player = DemoPlayer(_prepare(spec, sources, tmp_path / "cache"), with_rtabmap=False)

    # When the first frame plays
    frame = next(event for event in player.events() if event.kind == "frame")

    # Then it has the dataset's display size (color frames stay usable by the pipeline)
    with Image.open(io.BytesIO(frame.jpeg)) as image:
        assert image.size == spec.display_size
