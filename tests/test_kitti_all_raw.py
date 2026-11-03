"""All public KITTI raw drives in the gallery registry, grey and colour."""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from surmap.demo.datasets import DATASETS, ImageModality, ensure_dataset
from surmap.demo.kitti_raw import KITTI_DRIVES


def test_every_public_raw_drive_is_registered_in_grey_and_color() -> None:
    # Given the generated drive list from KITTI's public bucket
    assert len(KITTI_DRIVES) >= 150

    # When every drive's gallery entries are inspected
    # Then each drive has one grey and one colour entry sharing one download
    for drive, _size in KITTI_DRIVES:
        if drive == "2011_09_26_drive_0009":
            continue  # the hand-written pair, covered by its own tests
        grey = DATASETS[f"kitti-{drive}"]
        color = DATASETS[f"kitti-{drive}-color"]
        assert grey.modality is ImageModality.GREY
        assert color.modality is ImageModality.COLOR
        assert grey.kitti_cameras == ("00", "01")
        assert color.kitti_cameras == ("02", "03")
        assert color.download_id == grey.dataset_id
        assert grey.zip_url.endswith(f"{drive}_sync.zip")
        assert grey.zip_size_bytes > 0
        assert grey.calibration is not None
        assert grey.provider == "KITTI"
        assert grey.license is not None and grey.license.name == "CC BY-NC-SA 3.0"


def test_the_hand_pinned_drive_is_not_registered_twice() -> None:
    # Given all registered KITTI entries
    kitti = [key for key in DATASETS if key.startswith("kitti")]

    # Then 156 drives × grey+colour exist exactly once (0009 is the hand pair)
    assert len(kitti) == 312
    assert "kitti-2011_09_26_drive_0009" not in DATASETS


def test_the_hand_pinned_drive_keeps_its_strict_sha() -> None:
    # Given the drive SurMap shipped first, pinned by hand
    grey = DATASETS["kitti-2011-09-26-drive-0009"]

    # Then its SHA is pinned upfront, not learned on first use
    assert grey.zip_sha256 == "909639de40540f1d9bd8e3c181d79556ee4852781aa4684999f4cda3f3ef2611"


def test_generated_drives_carry_a_remote_thumbnail_and_gps_centre() -> None:
    # Given a generated drive that was never downloaded
    drive, _ = KITTI_DRIVES[0]
    grey = DATASETS[f"kitti-{drive}"]

    # Then the gallery can show KITTI's own thumbnail and an approximate map centre
    assert grey.thumbnail_url.endswith(f"{drive}/thumbnails/00.jpg")
    assert grey.gps_centre is not None
    assert grey.location_label != ""


def test_a_generated_drive_learns_its_sha_on_first_fetch_and_refuses_a_swap(
    tmp_path: Path,
) -> None:
    # Given a generated-style drive (size pinned, SHA empty) and a tiny zip for it
    from tests.test_kitti_colour_gps import _drive_zip

    drive_zip = tmp_path / "drive.zip"
    _drive_zip(drive_zip)
    calib_zip = tmp_path / "calib.zip"
    with zipfile.ZipFile(calib_zip, "w") as archive:
        from tests.test_kitti_colour_gps import CALIB

        archive.writestr("2011_09_26/calib_cam_to_cam.txt", CALIB)
    data = drive_zip.read_bytes()
    pinned = DATASETS["kitti-2011-09-26-drive-0009"]
    assert pinned.calibration is not None
    grey = replace(
        pinned,
        dataset_id="kitti-learned",
        zip_url="https://example.invalid/drive.zip",
        zip_size_bytes=len(data),
        zip_sha256="",
        calibration=replace(
            pinned.calibration,
            url="https://example.invalid/calib.zip",
            size_bytes=calib_zip.stat().st_size,
            sha256=hashlib.sha256(calib_zip.read_bytes()).hexdigest(),
        ),
    )
    color = replace(
        grey,
        dataset_id="kitti-learned-color",
        modality=ImageModality.COLOR,
        kitti_cameras=("02", "03"),
        download_id="kitti-learned",
    )
    sources = {
        "https://example.invalid/drive.zip": drive_zip,
        "https://example.invalid/calib.zip": calib_zip,
    }

    def fetch(url: str, target: Path) -> None:
        target.write_bytes(sources[url].read_bytes())

    # When the grey variant is prepared, its SHA is learned
    ensure_dataset(grey, tmp_path / "cache", log=lambda _: None, fetch=fetch)
    learned = (tmp_path / "cache" / "downloads" / "kitti-learned.zip.sha256").read_text().strip()
    assert learned == hashlib.sha256(data).hexdigest()

    # And when the shared zip is swapped for different bytes of the same size
    tampered = tmp_path / "tampered.zip"
    raw = bytearray(data)
    raw[len(raw) // 2] ^= 0xFF
    tampered.write_bytes(bytes(raw))
    sources["https://example.invalid/drive.zip"] = tampered
    (tmp_path / "cache" / "downloads" / "kitti-learned.zip").write_bytes(bytes(raw))

    # Then preparing the colour variant refuses it against the learned SHA
    with pytest.raises(ValueError, match="SHA-256"):
        ensure_dataset(color, tmp_path / "cache", log=lambda _: None, fetch=fetch)
