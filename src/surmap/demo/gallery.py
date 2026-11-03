"""Dataset gallery catalogue: one entry per registered dataset, for the page and the agent.

A new data source joins the gallery by adding one `DatasetSpec` to
`surmap.demo.datasets.DATASETS` with its `provider`, `license`, `modality`
and (when it has one) `gps_centre` set: this module, the chat gallery and
the agent's dataset tools all read the same entries, so no other code
changes. Thumbnails and GPS tracks appear once the dataset is prepared in
the cache; licence, provider and the approximate GPS centre are known
before any download.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from surmap.demo.datasets import (
    DATASETS,
    DatasetSpec,
    GeoPoint,
    ImageModality,
    LicenseInfo,
    PreparedDataset,
    cached_dataset,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["GalleryEntry", "dataset_thumbnail", "gallery_entries"]

MAX_TRACK_POINTS = 64
"""The most GPS points a gallery entry carries; the preview only needs the shape."""


@dataclass(frozen=True)
class GalleryEntry:
    """Everything one gallery card (and one agent dataset answer) shows."""

    dataset_id: str
    title: str
    description: str
    provider: str
    license: LicenseInfo | None
    credit: str
    modality: ImageModality
    official_url: str
    default_prompt: str
    prepared: bool
    frame_count: int
    thumbnail_available: bool
    location_label: str
    gps_centre: GeoPoint | None
    gps_track: tuple[GeoPoint, ...]


def gallery_entries(
    cache_dir: Path,
    *,
    catalog: Mapping[str, DatasetSpec] = DATASETS,
    prepared: Mapping[str, PreparedDataset] | None = None,
) -> tuple[GalleryEntry, ...]:
    """Every catalogue dataset as a gallery entry, in catalogue order.

    `prepared` overrides the cache lookup (tests, a host that already holds
    its scenes); otherwise a scene counts as prepared when its manifest is
    in `cache_dir`.
    """
    entries: list[GalleryEntry] = []
    for spec in catalog.values():
        found = prepared.get(spec.dataset_id) if prepared is not None else None
        if found is None and prepared is None:
            found = cached_dataset(spec, cache_dir)
        entries.append(_entry(spec, found))
    return tuple(entries)


def dataset_thumbnail(prepared: PreparedDataset, *, max_side: int = 480) -> bytes:
    """The first left frame as a JPEG thumbnail, colour kept for colour datasets.

    Cached as `thumbnail.jpg` at the dataset root; grey datasets get a grey
    JPEG, colour datasets an RGB one.
    """
    cached = prepared.root / "thumbnail.jpg"
    if cached.is_file():
        return cached.read_bytes()
    if not prepared.timestamps_ns:
        raise ValueError(f"{prepared.spec.dataset_id} has no frames for a thumbnail")
    source = prepared.frame_path(0, prepared.timestamps_ns[0])
    with Image.open(source) as frame:
        image = frame.convert("RGB" if prepared.spec.modality is ImageModality.COLOR else "L")
        image.thumbnail((max_side, max_side))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
    data = buffer.getvalue()
    cached.write_bytes(data)
    return data


def _entry(spec: DatasetSpec, prepared: PreparedDataset | None) -> GalleryEntry:
    track: tuple[GeoPoint, ...] = ()
    centre: GeoPoint | None = None
    if spec.gps_centre is not None:
        centre = GeoPoint(lon=spec.gps_centre[0], lat=spec.gps_centre[1])
    if prepared is not None:
        track = _downsampled(prepared.gps_track())
        if track:
            centre = GeoPoint(
                lon=sum(point.lon for point in track) / len(track),
                lat=sum(point.lat for point in track) / len(track),
            )
    return GalleryEntry(
        dataset_id=spec.dataset_id,
        title=spec.title,
        description=spec.description,
        provider=spec.provider or spec.title,
        license=spec.license,
        credit=spec.credit,
        modality=spec.modality,
        official_url=spec.official_url,
        default_prompt=spec.sam_prompt,
        prepared=prepared is not None,
        frame_count=len(prepared.timestamps_ns) if prepared is not None else 0,
        thumbnail_available=prepared is not None and bool(prepared.timestamps_ns),
        location_label=spec.location_label,
        gps_centre=centre,
        gps_track=track,
    )


def _downsampled(track: tuple[GeoPoint, ...]) -> tuple[GeoPoint, ...]:
    if len(track) <= MAX_TRACK_POINTS:
        return track
    step = len(track) / MAX_TRACK_POINTS
    return tuple(track[int(index * step)] for index in range(MAX_TRACK_POINTS))
