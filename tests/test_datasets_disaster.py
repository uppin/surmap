"""Disaster dataset downloaders: listings, selection, verified resumable downloads, CLI.

Every request goes to an in-memory fake transport; no socket is opened.
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.parse
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest

from surmap.datasets import cli
from surmap.datasets.disaster import (
    BOREAL_AUTHORIZE_URL,
    BOREAL_DATASET_ID,
    BOREAL_FILES_URL,
    BOREAL_PACKAGES_URL,
    NOAA_BUCKET_URL,
    NOAA_EVENT,
    NOAA_FIRES,
    NOAA_PREFIX,
    DatasetError,
    Plan,
    RemoteFile,
    Stream,
    boreal_cache_dir,
    boreal_listing,
    boreal_package_plan,
    boreal_packages,
    boreal_plan,
    boreal_resolver,
    download_plan,
    extract_package,
    list_bucket,
    noaa_cache_dir,
    safe_target,
    select_boreal,
    select_noaa,
    tile_bbox,
)

_ROOT = "/Boreal-Forest-Fire/"
_A = "Boreal-Forest-Fire-Subset-A"
_B = "Boreal-Forest-Fire-Subset-B"
_C = "Boreal-Forest-Fire-Subset-C"


def _body(name: str) -> bytes:
    return f"bytes of {name}\n".encode() * 3


def _boreal_paths() -> list[str]:
    return [
        f"{_A}/image_counts.txt",
        f"{_A}/Evo-Images/evoDJI_0001_frame2.jpg",
        f"{_A}/Evo-Labels/evoDJI_0001_frame2.txt",
        f"{_A}/Evo-Images/evoDJI_0001_frame10.jpg",
        f"{_A}/Evo-Labels/evoDJI_0001_frame10.txt",
        f"{_A}/Heinola-Images/heinola_DJI_0001_frame0.jpg",
        f"{_A}/Heinola-Labels/heinola_DJI_0001_frame0.txt",
        f"{_B}/Video-Ground-Truth/video-ground-truths.csv",
        f"{_B}/Evo-Videos/evo_10.mp4",
        f"{_B}/Evo-Videos/evo_2.mp4",
        f"{_B}/Heinola-Videos/heinola_1.mp4",
        f"{_C}/images/test/evoDJI_0001_frame123.jpg",
        f"{_C}/labels/test/evoDJI_0001_frame123.txt",
        f"{_C}/manual_masks/test/evoDJI_0001_frame123.png",
        f"{_C}/sam_masks/test/evoDJI_0001_frame123.png",
        f"{_C}/images/test/evoDJI_0001_frame128.jpg",
        f"{_C}/labels/test/evoDJI_0001_frame128.txt",
        f"{_C}/images/train/evoDJI_0002_frame1.jpg",
        f"{_C}/labels/train/evoDJI_0002_frame1.txt",
        "Visualisation-And-Coordinate-Conversion-Notebook/notebook.ipynb",
    ]


_TILES = {
    # name: size; palisades tiles first, then eaton (one tiny, one huge)
    "20250128aC1183345w340345n.tif": 300,
    "20250128aC1183300w340345n.tif": 200,
    "20250128aC1183345w340430n.tif": 100,
    "20250128aC1180215w341200n.tif": 50,
    "20250128aC1180000w341115n.tif": 5_000,
}
_SIDECARS = {
    "tile_index_20250128a_RGB.shp": 10,
    "tile_index_20250128a_RGB.dbf": 10,
    "cogs_20250128a_RGB.vrt": 10,
    "raw/153394_0128251757093_005_RGB1.jpg": 10,
}


class _FakeNet:
    """Metax, Etsin authorize, Fairdata download, and S3 (paged), counted."""

    def __init__(self, *, ranges: bool = True, page: int = 4) -> None:
        self.ranges = ranges
        self.page = page
        self.blobs: dict[str, bytes] = {}
        self.fetches: list[tuple[str, Mapping[str, object] | None]] = []
        self.streams: list[tuple[str, int]] = []
        self.metax: list[dict[str, object]] = []
        for rel in _boreal_paths():
            body = _body(rel)
            self.metax.append(
                {
                    "pathname": _ROOT + rel,
                    "size": len(body),
                    "checksum": "sha256:" + hashlib.sha256(body).hexdigest(),
                }
            )
            self.blobs[_ROOT + rel] = body
        self.keys: list[tuple[str, int, str]] = []
        for name, size in {**_TILES, **_SIDECARS}.items():
            key = NOAA_PREFIX + name
            body = (name.encode() * (size // len(name) + 1))[:size]
            etag = hashlib.md5(body).hexdigest() if size != 300 else "0" * 32 + "-2"
            self.keys.append((key, size, etag))
            self.blobs[f"{NOAA_BUCKET_URL}/{key}"] = body

    def fetch(self, url: str, *, json_body: Mapping[str, object] | None = None) -> bytes:
        self.fetches.append((url, json_body))
        if url == BOREAL_FILES_URL:
            return json.dumps(self.metax).encode()
        if url == BOREAL_PACKAGES_URL:
            return json.dumps({"partial": self.packages()}).encode()
        if url == BOREAL_AUTHORIZE_URL:
            assert json_body is not None and json_body["cr_id"] == BOREAL_DATASET_ID
            if "package" in json_body:
                return json.dumps(
                    {
                        "url": f"https://download.fairdata.fi/download?token=pkg-{json_body['package']}"
                    }
                ).encode()
            token = urllib.parse.quote(str(json_body["file"]), safe="")
            return json.dumps(
                {"url": f"https://download.fairdata.fi/download?token={token}"}
            ).encode()
        if url.startswith(NOAA_BUCKET_URL + "/?"):
            return self._list(dict(urllib.parse.parse_qsl(url.split("?", 1)[1])))
        raise AssertionError(f"unexpected fetch {url}")

    def zip_of(self, folder: str) -> bytes:
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            for path, body in self.blobs.items():
                if path.startswith(f"{_ROOT}{folder}/"):
                    archive.writestr(path.lstrip("/"), body)
        return out.getvalue()

    def packages(self) -> list[dict[str, object]]:
        seg = self.zip_of(_C)
        return [
            {
                "status": "SUCCESS",
                "package": "seg.zip",
                "size": len(seg),
                "checksum": "sha256:" + hashlib.sha256(seg).hexdigest(),
                "scope": [f"{_ROOT}{_C}"],
            },
            {"status": "PENDING", "package": "a.zip", "size": 1, "scope": [f"{_ROOT}{_A}"]},
            {"status": "SUCCESS", "package": "two.zip", "size": 1, "scope": ["/x", "/y"]},
        ]

    def _list(self, query: dict[str, str]) -> bytes:
        keys = [k for k in self.keys if k[0].startswith(query["prefix"])]
        start = int(query.get("continuation-token", "0"))
        chunk = keys[start : start + self.page]
        more = start + self.page < len(keys)
        rows = "".join(
            f"<Contents><Key>{key}</Key><LastModified>x</LastModified>"
            f"<ETag>&quot;{etag}&quot;</ETag><ChecksumAlgorithm>CRC64NVME</ChecksumAlgorithm>"
            f"<Size>{size}</Size></Contents>"
            for key, size, etag in chunk
        )
        token = (
            f"<NextContinuationToken>{start + self.page}</NextContinuationToken>" if more else ""
        )
        return (
            '<?xml version="1.0"?><ListBucketResult '
            'xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<IsTruncated>{'true' if more else 'false'}</IsTruncated>{token}{rows}"
            "</ListBucketResult>"
        ).encode()

    def stream(self, url: str, *, start: int = 0) -> Stream:
        self.streams.append((url, start))
        if url == "https://download.fairdata.fi/download?token=pkg-seg.zip":
            return Stream(status=200, chunks=[self.zip_of(_C)])
        if url.startswith("https://download.fairdata.fi/download?token="):
            body = self.blobs[urllib.parse.unquote(url.split("token=", 1)[1])]
            return Stream(status=200, chunks=[body[:7], body[7:]])
        body = self.blobs[url]
        if start and self.ranges:
            return Stream(status=206, chunks=[body[start:]])
        return Stream(status=200, chunks=[body])


# --------------------------------------------------------------------------- Boreal


def test_boreal_listing_maps_metax_paths_and_checksums() -> None:
    files = boreal_listing(_FakeNet())

    first = files[0]
    assert first.relpath == f"{_A}/image_counts.txt"
    assert first.source == _ROOT + first.relpath
    assert first.sha256 == hashlib.sha256(_body(first.relpath)).hexdigest()


def test_segmentation_limit_counts_samples_with_their_masks() -> None:
    files = boreal_listing(_FakeNet())

    picked = select_boreal(files, subsets=["segmentation"], splits=["test"], limit=1)

    assert [item.relpath.split("/", 1)[1] for item in picked] == [
        "images/test/evoDJI_0001_frame123.jpg",
        "labels/test/evoDJI_0001_frame123.txt",
        "manual_masks/test/evoDJI_0001_frame123.png",
        "sam_masks/test/evoDJI_0001_frame123.png",
    ]


def test_bbox_site_filter_natural_order_and_always_files() -> None:
    files = boreal_listing(_FakeNet())

    picked = select_boreal(files, subsets=["bbox"], sites=["evo"], limit=1)

    assert [item.relpath for item in picked] == [
        f"{_A}/image_counts.txt",
        f"{_A}/Evo-Images/evoDJI_0001_frame2.jpg",
        f"{_A}/Evo-Labels/evoDJI_0001_frame2.txt",
    ]


def test_videos_keep_ground_truth_and_sort_naturally() -> None:
    files = boreal_listing(_FakeNet())

    picked = select_boreal(files, subsets=["videos"], limit=2)

    assert [item.relpath.split("/", 1)[1] for item in picked] == [
        "Video-Ground-Truth/video-ground-truths.csv",
        "Evo-Videos/evo_2.mp4",
        "Evo-Videos/evo_10.mp4",
    ]


def test_boreal_selection_rejects_bad_arguments() -> None:
    files = boreal_listing(_FakeNet())
    with pytest.raises(DatasetError, match="unknown Boreal subset"):
        select_boreal(files, subsets=["everything"])
    with pytest.raises(DatasetError, match="at least 1"):
        select_boreal(files, subsets=["videos"], limit=0)


def test_boreal_download_authorizes_each_file_verifies_and_skips_on_rerun(
    tmp_path: Path,
) -> None:
    net = _FakeNet()
    plan = boreal_plan(net, splits=["test"], limit=1, cache_dir=tmp_path)

    result = download_plan(plan, net, resolve=boreal_resolver(net), resumable=False)
    authorized = [body["file"] for url, body in net.fetches if body is not None]
    streams = len(net.streams)
    again = download_plan(plan, net, resolve=boreal_resolver(net), resumable=False)

    assert (result.downloaded, result.skipped) == (4, 0)
    assert authorized == [item.source for item in plan.files]
    image = tmp_path / _C / "images/test/evoDJI_0001_frame123.jpg"
    assert image.read_bytes() == _body(f"{_C}/images/test/evoDJI_0001_frame123.jpg")
    assert not list(tmp_path.rglob("*.part"))
    assert (again.downloaded, again.skipped) == (0, 4)
    assert len(net.streams) == streams  # nothing re-fetched


def test_checksum_mismatch_removes_the_part_file(tmp_path: Path) -> None:
    net = _FakeNet()
    item = RemoteFile(relpath="a/b.bin", size=6, source="x", sha256="0" * 64)
    net.blobs["x"] = b"sixsix"
    plan = Plan(dataset="t", root=tmp_path, files=(item,))

    with pytest.raises(DatasetError, match="SHA-256"):
        download_plan(plan, net, retries=0)

    assert not (tmp_path / "a" / "b.bin").exists()
    assert not (tmp_path / "a" / "b.bin.part").exists()


def test_a_failed_file_is_retried_with_a_fresh_url(tmp_path: Path) -> None:
    net = _FakeNet()
    net.blobs["ok"] = b"payload"
    urls = iter(["broken", "ok"])
    item = RemoteFile(relpath="f.bin", size=7, source="unused")
    waits: list[float] = []

    def resolve(_: RemoteFile) -> str:
        return next(urls)

    def flaky(url: str, *, start: int = 0) -> Stream:
        if url == "broken":
            raise ConnectionResetError("TLS EOF")
        return Stream(status=200, chunks=[net.blobs[url]])

    net.stream = flaky  # type: ignore[method-assign]
    result = download_plan(
        Plan(dataset="t", root=tmp_path, files=(item,)), net, resolve=resolve, sleep=waits.append
    )

    assert result.downloaded == 1
    assert (tmp_path / "f.bin").read_bytes() == b"payload"
    assert waits == [2.0]


def test_unsafe_remote_paths_are_refused(tmp_path: Path) -> None:
    for bad in ("../escape.txt", "/etc/passwd", "a/../../b", ""):
        with pytest.raises(DatasetError, match="unsafe"):
            safe_target(tmp_path, bad)


def test_only_finished_single_folder_packages_are_offered() -> None:
    packages = boreal_packages(_FakeNet())

    assert list(packages) == [_C]
    assert packages[_C].relpath == "packages/seg.zip"
    assert packages[_C].sha256 is not None


def test_package_plan_skips_cached_subsets_and_refuses_missing_packages(tmp_path: Path) -> None:
    net = _FakeNet()
    plan, expected = boreal_package_plan(net, subsets=["segmentation"], cache_dir=tmp_path)
    assert [item.source for item in plan.files] == ["seg.zip"]
    assert {item.relpath.split("/", 1)[0] for item in expected} == {_C}
    with pytest.raises(DatasetError, match="no ready-made package"):
        boreal_package_plan(net, subsets=["bbox"], cache_dir=tmp_path)

    for item in expected:
        target = tmp_path / item.relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * item.size)
    again, _ = boreal_package_plan(net, subsets=["segmentation"], cache_dir=tmp_path)
    assert again.files == ()


def test_extract_package_checks_members_against_the_listing(tmp_path: Path) -> None:
    net = _FakeNet()
    zip_path = tmp_path / "seg.zip"
    zip_path.write_bytes(net.zip_of(_C))
    expected = [f for f in boreal_listing(net) if f.relpath.startswith(_C)]

    assert extract_package(zip_path, tmp_path / "out", expected) == len(expected)
    assert extract_package(zip_path, tmp_path / "out", expected) == 0  # already there
    with pytest.raises(DatasetError, match="unexpected file"):
        extract_package(zip_path, tmp_path / "other", expected[:1])


def test_cli_package_mode_downloads_unpacks_and_drops_the_zip(tmp_path: Path) -> None:
    net = _FakeNet()

    code = cli.main(["boreal", "--package", "--cache-dir", str(tmp_path)], transport=net)

    assert code == 0
    assert (tmp_path / _C / "images/test/evoDJI_0001_frame123.jpg").read_bytes() == _body(
        f"{_C}/images/test/evoDJI_0001_frame123.jpg"
    )
    assert not (tmp_path / "packages").exists()
    assert (tmp_path / "ATTRIBUTION.md").is_file()
    assert cli.main(["boreal", "--package", "--limit", "2"], transport=net) == 2


# --------------------------------------------------------------------------- NOAA


def test_tile_name_is_its_north_west_corner() -> None:
    bbox = tile_bbox("20250128aC1180215w341200n.tif")

    assert bbox is not None
    west, south, east, north = bbox
    assert west == pytest.approx(-(118 + 2 / 60 + 15 / 3600))
    assert north == pytest.approx(34.2)
    assert east - west == pytest.approx(0.0125)
    assert north - south == pytest.approx(0.0125)
    assert tile_bbox("cogs_20250128a_RGB.vrt") is None


def test_bucket_listing_follows_continuation_and_keeps_only_plain_md5() -> None:
    net = _FakeNet(page=3)

    files = list_bucket(net, NOAA_PREFIX, strip=NOAA_EVENT)

    assert len(files) == len(_TILES) + len(_SIDECARS)
    assert sum(1 for url, _ in net.fetches if url.startswith(NOAA_BUCKET_URL)) == 3
    by_name = {item.relpath.rsplit("/", 1)[1]: item for item in files}
    assert by_name["20250128aC1183345w340345n.tif"].md5 is None  # multipart ETag
    assert by_name["20250128aC1183300w340345n.tif"].md5 is not None
    assert by_name["20250128aC1180215w341200n.tif"].relpath.startswith("20250128a_RGB/")


def test_noaa_selection_by_fire_bbox_limit_and_size() -> None:
    files = list_bucket(_FakeNet(), NOAA_PREFIX, strip=NOAA_EVENT)

    def names(picked: list[RemoteFile]) -> list[str]:
        return [item.relpath.rsplit("/", 1)[1] for item in picked]

    palisades = select_noaa(files, fire="palisades", limit=2)
    eaton = select_noaa(files, fire="eaton", max_tile_bytes=1000, include_index=False)
    boxed = select_noaa(files, bbox=(-118.57, 34.065, -118.55, 34.07), include_index=False)

    assert names(palisades) == [
        "tile_index_20250128a_RGB.shp",
        "tile_index_20250128a_RGB.dbf",
        "20250128aC1183345w340430n.tif",  # northernmost row first
        "20250128aC1183345w340345n.tif",  # then the next row south
    ]
    assert names(eaton) == ["20250128aC1180215w341200n.tif"]
    assert names(boxed) == ["20250128aC1183345w340430n.tif"]
    assert "raw/" not in " ".join(item.relpath for item in palisades)


def test_noaa_selection_needs_an_area() -> None:
    with pytest.raises(DatasetError, match="--fire or a --bbox"):
        select_noaa([])
    with pytest.raises(DatasetError, match="unknown fire"):
        select_noaa([], fire="woolsey")
    with pytest.raises(DatasetError, match="WEST SOUTH EAST NORTH"):
        select_noaa([], bbox=(-118.0, 34.2, -118.5, 34.0))


def test_fire_areas_do_not_overlap() -> None:
    pal, eat = NOAA_FIRES["palisades"], NOAA_FIRES["eaton"]
    assert pal[2] < eat[0]


def test_partial_noaa_tile_resumes_with_a_range_request(tmp_path: Path) -> None:
    net = _FakeNet()
    item = next(f for f in list_bucket(net, NOAA_PREFIX, strip=NOAA_EVENT) if f.size == 100)
    target = tmp_path / item.relpath
    target.parent.mkdir(parents=True)
    body = net.blobs[item.source]
    target.with_name(target.name + ".part").write_bytes(body[:40])

    result = download_plan(Plan(dataset="t", root=tmp_path, files=(item,)), net)

    assert net.streams == [(item.source, 40)]
    assert result.bytes_written == 60
    assert target.read_bytes() == body


def test_server_without_ranges_restarts_the_part_file(tmp_path: Path) -> None:
    net = _FakeNet(ranges=False)
    item = next(f for f in list_bucket(net, NOAA_PREFIX, strip=NOAA_EVENT) if f.size == 100)
    target = tmp_path / item.relpath
    target.parent.mkdir(parents=True)
    target.with_name(target.name + ".part").write_bytes(b"stale garbage")

    download_plan(Plan(dataset="t", root=tmp_path, files=(item,)), net)

    assert target.read_bytes() == net.blobs[item.source]


def test_short_download_keeps_the_part_file_for_a_resume(tmp_path: Path) -> None:
    net = _FakeNet()
    net.blobs["short"] = b"abc"
    item = RemoteFile(relpath="t.tif", size=10, source="short")

    with pytest.raises(DatasetError, match="rerun to resume"):
        download_plan(Plan(dataset="t", root=tmp_path, files=(item,)), net, retries=0)

    assert (tmp_path / "t.tif.part").read_bytes() == b"abc"
    assert not (tmp_path / "t.tif").exists()


# --------------------------------------------------------------------------- CLI + cache


def test_cache_dirs_default_under_surmap_and_follow_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SURMAP_BOREAL_CACHE", raising=False)
    monkeypatch.delenv("SURMAP_NOAA_ERI_CACHE", raising=False)
    assert boreal_cache_dir() == Path.home() / ".cache" / "surmap" / "boreal-fire"
    assert noaa_cache_dir() == Path.home() / ".cache" / "surmap" / "noaa-eri-2025"
    monkeypatch.setenv("SURMAP_NOAA_ERI_CACHE", str(tmp_path))
    assert noaa_cache_dir() == tmp_path


def test_cli_dry_run_lists_sizes_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    net = _FakeNet()

    code = cli.main(
        ["noaa", "--fire", "palisades", "--limit", "1", "--dry-run", "--cache-dir", str(tmp_path)],
        transport=net,
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "20250128aC1183345w340430n.tif" in out
    assert "noaa-eri-2025: 3 files" in out
    assert net.streams == []
    assert not any(tmp_path.iterdir())


def test_cli_downloads_with_attribution_for_each_dataset(tmp_path: Path) -> None:
    net = _FakeNet()
    boreal_dir, noaa_dir = tmp_path / "boreal", tmp_path / "noaa"

    assert cli.main(["boreal", "--videos", "1", "--cache-dir", str(boreal_dir)], transport=net) == 0
    assert (
        cli.main(
            ["noaa", "--fire", "eaton", "--max-tile-mb", "0.001", "--cache-dir", str(noaa_dir)],
            transport=net,
        )
        == 0
    )

    assert (boreal_dir / _B / "Evo-Videos" / "evo_2.mp4").is_file()
    assert (boreal_dir / _B / "Video-Ground-Truth" / "video-ground-truths.csv").is_file()
    assert not (boreal_dir / _B / "Evo-Videos" / "evo_10.mp4").exists()
    boreal_note = (boreal_dir / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert "CC BY 4.0" in boreal_note and "10.1038/s41597-025-05634-0" in boreal_note
    assert (noaa_dir / "20250128a_RGB" / "20250128aC1180215w341200n.tif").is_file()
    noaa_note = (noaa_dir / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert "CC0-1.0" in noaa_note and "inport/item/74399" in noaa_note


def test_cli_sizes_and_errors(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    net = _FakeNet()

    assert cli.main(["boreal", "--sizes"], transport=net) == 0
    assert "segmentation" in capsys.readouterr().out
    assert cli.main(["noaa", "--cache-dir", str(tmp_path)], transport=net) == 2
    assert "--fire or a --bbox" in capsys.readouterr().err
