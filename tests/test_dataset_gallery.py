"""Dataset gallery catalogue: extensible metadata, licence, thumbnail, GPS preview."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from surmap.demo.datasets import (
    DATASETS,
    DatasetSpec,
    GeoPoint,
    ImageModality,
    LicenseInfo,
    PreparedDataset,
)
from surmap.demo.gallery import dataset_thumbnail, gallery_entries


def test_the_registry_describes_kitti_in_grey_and_color_with_its_licence() -> None:
    # Given / When the KITTI entries are read
    grey = DATASETS["kitti-2011-09-26-drive-0009"]
    color = DATASETS["kitti-2011-09-26-drive-0009-color"]

    # Then both modalities exist, share one download, and carry licence + GPS centre
    assert grey.modality is ImageModality.GREY
    assert color.modality is ImageModality.COLOR
    assert color.zip_url == grey.zip_url and color.zip_sha256 == grey.zip_sha256
    assert grey.license is not None and grey.license.name == "CC BY-NC-SA 3.0"
    assert color.license == grey.license
    assert grey.provider == "KITTI"
    assert grey.gps_centre is not None
    assert grey.location_label != ""


def test_every_registry_entry_carries_provider_licence_and_modality() -> None:
    # Given / When every registered dataset is inspected
    # Then a new source only needs one spec: provider, licence and modality are always present
    for spec in DATASETS.values():
        assert spec.provider != "", spec.dataset_id
        assert spec.license is not None, spec.dataset_id
        assert spec.license.name != "" and spec.license.attribution != ""
        assert isinstance(spec.modality, ImageModality)


def test_a_gallery_entry_exposes_thumbnail_licence_and_gps_for_the_page(
    tmp_path: Path,
) -> None:
    # Given a prepared KITTI-like scene with a GPS track on disk
    spec = DATASETS["kitti-2011-09-26-drive-0009-color"]
    prepared = _prepared(tmp_path, spec, gps=((8.42, 49.01), (8.43, 49.02)))

    # When the gallery is built for a cache holding that scene
    entries = gallery_entries(
        tmp_path, catalog={spec.dataset_id: spec}, prepared={spec.dataset_id: prepared}
    )

    # Then the entry carries everything a card renders without opening the dataset
    (entry,) = entries
    assert entry.dataset_id == spec.dataset_id
    assert entry.modality is ImageModality.COLOR
    assert entry.license is not None and "CC BY-NC-SA" in entry.license.name
    assert entry.prepared is True
    assert entry.frame_count == 2
    assert entry.thumbnail_available is True
    assert entry.gps_track[0] == GeoPoint(lon=8.42, lat=49.01)
    assert entry.gps_centre == GeoPoint(lon=8.425, lat=49.015)


def test_an_unprepared_entry_still_shows_licence_and_static_gps_centre(tmp_path: Path) -> None:
    # Given a registered but never-downloaded dataset
    spec = DATASETS["kitti-2011-09-26-drive-0009"]

    # When the gallery is built from an empty cache
    (entry,) = gallery_entries(tmp_path, catalog={spec.dataset_id: spec})

    # Then licence and map centre are known, but no thumbnail or track is claimed
    assert entry.prepared is False
    assert entry.thumbnail_available is False
    assert entry.gps_track == ()
    assert entry.gps_centre is not None
    assert entry.license is not None


def test_a_thumbnail_keeps_color_for_color_datasets(tmp_path: Path) -> None:
    # Given a prepared color scene whose first frame is distinctly red
    spec = DATASETS["kitti-2011-09-26-drive-0009-color"]
    prepared = _prepared(tmp_path, spec, rgb=(200, 30, 30))

    # When its thumbnail is rendered
    jpeg = dataset_thumbnail(prepared)

    # Then the thumbnail is a color JPEG, not a greyscale one
    with Image.open(io.BytesIO(jpeg)) as image:
        assert image.mode == "RGB"
        pixel = image.convert("RGB").getpixel((2, 2))
        assert isinstance(pixel, tuple)
        red, green, blue = pixel
        assert red > 150 and green < 90 and blue < 90


def test_the_gallery_is_open_to_a_new_source_with_one_spec(tmp_path: Path) -> None:
    # Given a dataset from a source the gallery has never heard of
    spec = DatasetSpec(
        dataset_id="acme-pond-01",
        title="Acme Pond 01",
        description="A pond survey.",
        zip_url="https://example.invalid/pond.zip",
        zip_size_bytes=1,
        zip_sha256="0" * 64,
        official_url="https://example.invalid/pond",
        provider="Acme",
        license=LicenseInfo(
            name="CC BY 4.0",
            url="https://creativecommons.org/licenses/by/4.0/",
            attribution="Acme Pond, CC BY 4.0",
        ),
        modality=ImageModality.COLOR,
    )

    # When it joins the catalogue
    (entry,) = gallery_entries(tmp_path, catalog={spec.dataset_id: spec})

    # Then it appears with its own licence, provider and modality, no code change needed
    assert entry.provider == "Acme"
    assert entry.license is not None and entry.license.name == "CC BY 4.0"
    assert entry.modality is ImageModality.COLOR


def _prepared(
    tmp_path: Path,
    spec: DatasetSpec,
    *,
    rgb: tuple[int, int, int] = (120, 120, 120),
    gps: tuple[tuple[float, float], ...] = (),
) -> PreparedDataset:
    root = tmp_path / spec.dataset_id
    stamps = (100, 200)
    for channel in (0, 1):
        folder = root / "mav0" / f"cam{channel}" / "data"
        folder.mkdir(parents=True, exist_ok=True)
        for stamp in stamps:
            mode = "RGB" if spec.modality is ImageModality.COLOR else "L"
            pixel = rgb if mode == "RGB" else rgb[0]
            Image.new(mode, (64, 48), pixel).save(
                root / "mav0" / f"cam{channel}" / "data" / f"{stamp}.png"
            )
    if gps:
        points = ", ".join(f"[{lon}, {lat}]" for lon, lat in gps)
        (root / "gps_track.json").write_text(f"[{points}]", encoding="utf-8")
    return PreparedDataset(spec, root, stamps)
