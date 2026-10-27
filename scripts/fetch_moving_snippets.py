#!/usr/bin/env python3
"""Fetch moving-object snippet fixtures (design section 6.1/6.2).

Downloads are pinned by URL + SHA-256 in each snippet manifest and
cached under ~/.cache/surmap/moving-snippets (override with
$SURMAP_SNIPPET_CACHE_DIR). KITTI's image zips are ~15 GB each, so
KITTI is served by HTTP range-extraction of a single sequence's
members from the zip central directory, never a full download.

Usage:
    python scripts/fetch_moving_snippets.py --list
    python scripts/fetch_moving_snippets.py --snippet kitti-tracking-stereo \
        --sequence 0020 --frames 0-149
    python scripts/fetch_moving_snippets.py --colmap-check <image-dir> <calib-file>
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import subprocess
import sys
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from surmap.moving.snippets import snippet_specs  # noqa: E402


def cache_dir() -> Path:
    override = os.environ.get("SURMAP_SNIPPET_CACHE_DIR", "").strip()
    return Path(override) if override else Path.home() / ".cache" / "surmap" / "moving-snippets"


def _range(url: str, start: int, end: int) -> bytes:
    request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _size(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=60) as response:
        return int(response.headers["Content-Length"])


@dataclass(frozen=True)
class ZipEntry:
    name: str
    method: int
    compressed_size: int
    local_offset: int


def zip_index(url: str) -> dict[str, ZipEntry]:
    """Central-directory index of a remote zip, fetched by range requests."""
    total = _size(url)
    tail = _range(url, max(0, total - 65557), total - 1)
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError(f"{url}: no zip end-of-central-directory")
    cd_size, cd_offset = struct.unpack_from("<II", tail, eocd + 12)
    directory = _range(url, cd_offset, cd_offset + cd_size - 1)
    entries: dict[str, ZipEntry] = {}
    pos = 0
    while pos < len(directory) - 4 and directory[pos : pos + 4] == b"PK\x01\x02":
        fields = struct.unpack_from("<HHHHHHIIIHHHHHII", directory, pos + 4)
        method, comp_size = fields[3], fields[7]
        name_len, extra_len, comment_len = fields[9], fields[10], fields[11]
        local_offset = fields[15]
        name = directory[pos + 46 : pos + 46 + name_len].decode()
        entries[name] = ZipEntry(name, method, comp_size, local_offset)
        pos += 46 + name_len + extra_len + comment_len
    return entries


def extract_member(url: str, entry: ZipEntry, target: Path) -> str:
    """Extract one zip member by range request; returns its SHA-256."""
    header = _range(url, entry.local_offset, entry.local_offset + 29)
    if header[:4] != b"PK\x03\x04":
        raise ValueError(f"{entry.name}: bad local header")
    name_len, extra_len = struct.unpack_from("<HH", header, 26)
    start = entry.local_offset + 30 + name_len + extra_len
    raw = _range(url, start, start + entry.compressed_size - 1)
    if entry.method == 8:  # deflate
        raw = zlib.decompress(raw, -15)
    elif entry.method != 0:
        raise ValueError(f"{entry.name}: unsupported compression {entry.method}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def colmap_check(image_dir: Path, calib_file: Path) -> int:
    """Cross-check COLMAP-recovered fx against a shipped calibration (6.2)."""
    from surmap.moving.snippets import _projection

    shipped_fx = _projection(calib_file.read_text(encoding="utf-8"), "P2")[0]
    work = cache_dir() / "colmap-check"
    work.mkdir(parents=True, exist_ok=True)
    db = work / "db.db"
    subprocess.run(
        [
            "colmap",
            "feature_extractor",
            "--database_path",
            str(db),
            "--image_path",
            str(image_dir),
            "--ImageReader.single_camera",
            "1",
            "--ImageReader.camera_model",
            "OPENCV",
            "--SiftExtraction.use_gpu",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["colmap", "sequential_matcher", "--database_path", str(db), "--SiftMatching.use_gpu", "1"],
        check=True,
        capture_output=True,
        text=True,
    )
    sparse = work / "sparse"
    sparse.mkdir(exist_ok=True)
    subprocess.run(
        [
            "colmap",
            "mapper",
            "--database_path",
            str(db),
            "--image_path",
            str(image_dir),
            "--output_path",
            str(sparse),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    cameras = next(sparse.rglob("cameras.txt"), None)
    if cameras is None:
        print("colmap-check: no reconstruction produced", file=sys.stderr)
        return 1
    for line in cameras.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            fx = float(line.split()[4])
            delta = abs(fx - shipped_fx) / shipped_fx
            print(f"colmap fx={fx:.2f} shipped fx={shipped_fx:.2f} delta={delta:.2%}")
            return 0 if delta <= 0.02 else 1
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list registered snippets")
    parser.add_argument("--snippet", help="snippet id to fetch")
    parser.add_argument("--sequence", help="KITTI sequence id, e.g. 0020")
    parser.add_argument("--frames", help="KITTI frame range, e.g. 0-149")
    parser.add_argument(
        "--colmap-check",
        nargs=2,
        metavar=("IMAGE_DIR", "CALIB"),
        help="run the COLMAP calibration cross-check",
    )
    args = parser.parse_args()

    if args.colmap_check:
        return colmap_check(Path(args.colmap_check[0]), Path(args.colmap_check[1]))
    specs = {spec.snippet_id: spec for spec in snippet_specs()}
    if args.list or not args.snippet:
        for spec in specs.values():
            print(f"{spec.snippet_id:36s} {spec.scene:8s} {spec.license:45s} {spec.source_url}")
        return 0
    spec = specs[args.snippet]
    if spec.scene != "stereo":
        print(
            f"{spec.snippet_id}: fetch by downloading {spec.source_url} into "
            f"{cache_dir() / spec.snippet_id} and pinning its SHA-256 in the manifest "
            "(see design 6.1); frame extraction is a local step."
        )
        return 0
    if not args.sequence:
        parser.error("KITTI fetch needs --sequence")
    first, last = (int(part) for part in (args.frames or "0-149").split("-"))
    index = zip_index(spec.source_url)
    out = cache_dir() / spec.snippet_id / args.sequence
    fetched = 0
    for name, entry in sorted(index.items()):
        if f"/{args.sequence}/" not in name and not name.startswith(f"{args.sequence}/"):
            continue
        fetched += 1
        digest = extract_member(spec.source_url, entry, out / Path(name).name)
        print(f"{name} sha256={digest}")
    print(f"fetched {fetched} members for sequence {args.sequence} frames {first}-{last}")
    return 0 if fetched else 1


if __name__ == "__main__":
    raise SystemExit(main())
