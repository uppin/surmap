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
import json
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


def _zip64_extra(extra: bytes) -> tuple[int, ...]:
    """Values from a zip64 extended-information extra field (tag 0x0001)."""
    pos = 0
    while pos + 4 <= len(extra):
        tag, size = struct.unpack_from("<HH", extra, pos)
        if tag == 0x0001:
            body = extra[pos + 4 : pos + 4 + size]
            return struct.unpack(f"<{len(body) // 8}Q", body[: len(body) // 8 * 8])
        pos += 4 + size
    return ()


def parse_central_directory(directory: bytes) -> dict[str, ZipEntry]:
    """Parse central-directory bytes, honouring zip64 extra fields."""
    entries: dict[str, ZipEntry] = {}
    pos = 0
    while pos < len(directory) - 4 and directory[pos : pos + 4] == b"PK\x01\x02":
        fields = struct.unpack_from("<HHHHHHIIIHHHHHII", directory, pos + 4)
        method = fields[3]
        comp_size, uncomp_size = fields[7], fields[8]
        name_len, extra_len, comment_len = fields[9], fields[10], fields[11]
        local_offset = fields[15]
        extra = directory[pos + 46 + name_len : pos + 46 + name_len + extra_len]
        if uncomp_size == 0xFFFFFFFF or comp_size == 0xFFFFFFFF or local_offset == 0xFFFFFFFF:
            zip64 = _zip64_extra(extra)
            cursor = 0
            if uncomp_size == 0xFFFFFFFF:
                uncomp_size, cursor = zip64[cursor], cursor + 1
            if comp_size == 0xFFFFFFFF:
                comp_size, cursor = zip64[cursor], cursor + 1
            if local_offset == 0xFFFFFFFF:
                local_offset = zip64[cursor]
        name = directory[pos + 46 : pos + 46 + name_len].decode()
        entries[name] = ZipEntry(name, method, comp_size, local_offset)
        pos += 46 + name_len + extra_len + comment_len
    return entries


def _central_directory_range(url: str, total: int, tail: bytes, tail_base: int) -> tuple[int, int]:
    """(offset, size) of the central directory, via EOCD or zip64 EOCD."""
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd >= 0:
        cd_size, cd_offset = struct.unpack_from("<II", tail, eocd + 12)
        if cd_size != 0xFFFFFFFF and cd_offset != 0xFFFFFFFF:
            return cd_offset, cd_size
    locator = tail.rfind(b"PK\x06\x07")
    if locator < 0:
        raise ValueError(f"{url}: no zip end-of-central-directory (classic or zip64)")
    z64_offset = struct.unpack_from("<Q", tail, locator + 8)[0]
    if z64_offset >= tail_base:
        record = tail[z64_offset - tail_base : z64_offset - tail_base + 56]
    else:
        record = _range(url, z64_offset, z64_offset + 55)
    if record[:4] != b"PK\x06\x06":
        raise ValueError(f"{url}: bad zip64 end-of-central-directory")
    cd_size, cd_offset = struct.unpack_from("<QQ", record, 40)
    return cd_offset, cd_size


def zip_index(url: str) -> dict[str, ZipEntry]:
    """Central-directory index of a remote zip, fetched by range requests."""
    total = _size(url)
    tail_base = max(0, total - 65557)
    tail = _range(url, tail_base, total - 1)
    cd_offset, cd_size = _central_directory_range(url, total, tail, tail_base)
    directory = _range(url, cd_offset, cd_offset + cd_size - 1)
    return parse_central_directory(directory)


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


def extract_span(url: str, entries: list[ZipEntry], out_dir: Path) -> dict[str, str]:
    """Extract a contiguous run of members with chunked range fetches.

    Sequence members sit contiguously in the zip, so one span
    fetch (in 8 MB chunks) replaces hundreds of per-member
    requests. Returns {member name: sha256}.
    """
    ordered = sorted(entries, key=lambda entry: entry.local_offset)
    start = ordered[0].local_offset
    end = max(entry.local_offset + entry.compressed_size + 1024 for entry in ordered)
    buffer = bytearray()
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + 8 * 1024 * 1024 - 1)
        buffer.extend(_range(url, cursor, chunk_end))
        cursor = chunk_end + 1
    digests: dict[str, str] = {}
    for entry in ordered:
        offset = entry.local_offset - start
        if bytes(buffer[offset : offset + 4]) != b"PK\x03\x04":
            raise ValueError(f"{entry.name}: bad local header in span")
        name_len, extra_len = struct.unpack_from("<HH", buffer, offset + 26)
        data_start = offset + 30 + name_len + extra_len
        raw = bytes(buffer[data_start : data_start + entry.compressed_size])
        if entry.method == 8:
            raw = zlib.decompress(raw, -15)
        elif entry.method != 0:
            raise ValueError(f"{entry.name}: unsupported compression {entry.method}")
        target = out_dir / Path(entry.name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        digests[entry.name] = hashlib.sha256(raw).hexdigest()
    return digests


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
    out = cache_dir() / spec.snippet_id / args.sequence
    manifest: dict[str, object] = {
        "snippet_id": spec.snippet_id,
        "sequence": args.sequence,
        "frames": [first, last],
        "files": {},
    }
    files: dict[str, str] = {}
    fetched = 0
    # Both stereo channels: image_02 (left) and image_03 (right).
    channel_zips = {
        "image_02": spec.source_url,
        "image_03": spec.source_url.replace("image_2.zip", "image_3.zip"),
    }
    for channel, zip_url in channel_zips.items():
        index = zip_index(zip_url)
        selected = [
            entry
            for name, entry in sorted(index.items())
            if name.startswith("training/")
            and f"/{args.sequence}/" in name
            and Path(name).stem.isdigit()
            and first <= int(Path(name).stem) <= last
        ]
        if not selected:
            continue
        digests = extract_span(zip_url, selected, out / channel)
        for name, digest in digests.items():
            files[f"{channel}/{Path(name).name}"] = digest
            fetched += 1
            print(f"{channel}/{name} sha256={digest}")
    manifest["files"] = files
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"fetched {fetched} members for sequence {args.sequence} frames {first}-{last}")
    return 0 if fetched else 1


if __name__ == "__main__":
    raise SystemExit(main())
