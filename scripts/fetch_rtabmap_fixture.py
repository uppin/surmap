#!/usr/bin/env python3
"""Fetch and prepare everything the real RTAB-Map E2Es need.

No RTAB-Map (or any native build) may be installed on the host, in CI
or locally: this script pulls the pinned RTAB-Map Docker image by
digest, and prepares a small EuRoC V1_01_easy stereo subset (90 pairs
at half resolution, sensor calibrations, and the IMU recording).

The prepared subset is hosted as a GitHub release asset on this repo
(`fixtures-euroc-v1`), because the upstream EuRoC host and its
HuggingFace mirror rate-limit the range requests the original cut
needed (HTTP 429 in CI). The asset is verified by SHA-256 before
use. `--from-upstream` regenerates the subset from the upstream
sequence zip with HTTP range requests — the zip itself is never
downloaded whole, and every extracted file is CRC-verified against
the zip's central directory; that is how a new asset is produced.

The prepared fixture lands in `tests/fixtures/euroc_v101_rtabmap/`
(git-ignored generated data; only the README next to it is committed):

    uv run python scripts/fetch_rtabmap_fixture.py
    SURMAP_REQUIRE_RTABMAP_E2E=1 uv run pytest tests/test_survey_cm5_rtabmap_e2e.py
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zlib
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "tests" / "fixtures" / "euroc_v101_rtabmap"

# The prepared subset, hosted on this repo's releases so CI never
# range-requests the rate-limited upstream hosts. Produced by running
# this script with --from-upstream and uploading the tarball of the
# output directory; verified by SHA-256 on every fetch.
FIXTURE_ASSET_URL = (
    "https://github.com/uppin/surmap/releases/download/fixtures-euroc-v1/euroc_v101_rtabmap.tar.gz"
)
FIXTURE_ASSET_SHA256 = "07963d35fd7bd15f0da9c99bf06c55c885e6a0edce513257e1344a3e1df2d244"
FIXTURE_ASSET_SIZE = 4_070_141

# The official EuRoC host (robotics.ethz.ch) serves this zip; the
# HuggingFace mirror below carries a byte copy and supports the range
# requests the subset cut needs. Files are CRC-verified either way.
EUROC_ZIP_URL = "https://huggingface.co/datasets/pepijn223/euroc-mirror/resolve/main/V1_01_easy.zip"
EUROC_ZIP_SIZE = 1_149_702_102
EUROC_OFFICIAL_URL = (
    "https://robotics.ethz.ch/~asl-datasets/ijrr_euroc_mav_dataset/"
    "vicon_room/vicon_room_1/V1_01_easy/V1_01_easy.zip"
)

PINNED_RTABMAP_IMAGE = (
    "introlab3it/rtabmap@sha256:14a58ac31565f0a0ab2421fa861f6fc43010e54345e13a6a1ccde32d3b0ffdb8"
)

FRAME_START = 400  # skip the stationary start; the MAV is moving here
FRAME_COUNT = 90
OUTPUT_WIDTH = 376  # half of EuRoC's 752x480, calibration scaled along
OUTPUT_HEIGHT = 240
JPEG_QUALITY = 85


def _range_bytes(url: str, start: int, end: int) -> bytes:
    request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return bytes(response.read())


def _zip_entries(url: str, total_size: int) -> dict[str, tuple[int, int, int, int, int]]:
    """name -> (method, compressed, uncompressed, local offset, crc32)."""
    tail = _range_bytes(url, total_size - 1_048_576, total_size - 1)
    eocd_at = tail.rfind(b"PK\x05\x06")
    if eocd_at < 0:
        raise RuntimeError("zip end-of-central-directory not found")
    _, _, _, _, _, cd_size, cd_offset, _ = struct.unpack("<IHHHHIIH", tail[eocd_at : eocd_at + 22])
    cd_start_in_tail = cd_offset - (total_size - len(tail))
    if cd_start_in_tail >= 0:
        directory = tail[cd_start_in_tail : cd_start_in_tail + cd_size]
    else:
        directory = _range_bytes(url, cd_offset, cd_offset + cd_size - 1)
    entries: dict[str, tuple[int, int, int, int, int]] = {}
    pos = 0
    while pos + 46 <= len(directory) and directory[pos : pos + 4] == b"PK\x01\x02":
        fields = struct.unpack("<IHHHHHHIIIHHHHHII", directory[pos : pos + 46])
        method, crc, csize, usize = fields[4], fields[7], fields[8], fields[9]
        name_len, extra_len, comment_len = fields[10], fields[11], fields[12]
        local_offset = fields[16]
        name = directory[pos + 46 : pos + 46 + name_len].decode()
        entries[name] = (method, csize, usize, local_offset, crc)
        pos += 46 + name_len + extra_len + comment_len
    if not entries:
        raise RuntimeError("zip central directory parsed to zero entries")
    return entries


def _extract(url: str, entries: dict[str, tuple[int, int, int, int, int]], name: str) -> bytes:
    method, csize, usize, local_offset, crc = entries[name]
    header = _range_bytes(url, local_offset, local_offset + 29)
    name_len, extra_len = struct.unpack("<HH", header[26:30])
    start = local_offset + 30 + name_len + extra_len
    raw = _range_bytes(url, start, start + csize - 1)
    data = zlib.decompress(raw, -15) if method == 8 else raw
    if len(data) != usize or zlib.crc32(data) & 0xFFFFFFFF != crc:
        raise RuntimeError(f"zip entry {name} failed size/CRC verification")
    return data


def _scaled_sensor_yaml(text: str) -> str:
    """The EuRoC sensor.yaml rewritten for half-resolution frames."""
    text = text.replace("resolution: [752, 480]", f"resolution: [{OUTPUT_WIDTH}, {OUTPUT_HEIGHT}]")

    def scale(match: re.Match[str]) -> str:
        values = [float(part) / 2 for part in match.group(1).split(",")]
        return "intrinsics: [" + ", ".join(str(value) for value in values) + "]"

    return re.sub(r"intrinsics: \[([^\]]+)\]", scale, text)


def _pull_image(image: str) -> None:
    subprocess.run(["docker", "pull", image], check=True)


def _fetch_asset(output: Path) -> None:
    """Download the prepared subset from this repo's release asset."""
    with urllib.request.urlopen(FIXTURE_ASSET_URL, timeout=300) as response:
        payload = bytes(response.read())
    if len(payload) != FIXTURE_ASSET_SIZE:
        raise RuntimeError(f"fixture asset size {len(payload)} != pinned {FIXTURE_ASSET_SIZE}")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != FIXTURE_ASSET_SHA256:
        raise RuntimeError(f"fixture asset SHA-256 {digest} != pinned {FIXTURE_ASSET_SHA256}")
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "extract"
        staging.mkdir()
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            archive.extractall(staging, filter="data")
        extracted = staging / DEFAULT_OUTPUT.name
        if not (extracted / "manifest.json").exists():
            raise RuntimeError("fixture asset has no manifest.json")
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(extracted, output)


def _prepare_from_upstream(output: Path, image: str) -> None:
    entries = _zip_entries(EUROC_ZIP_URL, EUROC_ZIP_SIZE)
    cam0_names = sorted(
        name for name in entries if name.startswith("mav0/cam0/data/") and name.endswith(".png")
    )
    chosen = cam0_names[FRAME_START : FRAME_START + FRAME_COUNT]
    if len(chosen) < FRAME_COUNT:
        raise RuntimeError(f"only {len(chosen)} EuRoC frames available from index {FRAME_START}")

    for channel in (0, 1):
        data_dir = output / "mav0" / f"cam{channel}" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        yaml_text = _extract(EUROC_ZIP_URL, entries, f"mav0/cam{channel}/sensor.yaml").decode()
        (output / "mav0" / f"cam{channel}" / "sensor.yaml").write_text(
            _scaled_sensor_yaml(yaml_text), encoding="utf-8"
        )
    imu_dir = output / "mav0" / "imu0"
    imu_dir.mkdir(parents=True, exist_ok=True)
    (imu_dir / "sensor.yaml").write_bytes(_extract(EUROC_ZIP_URL, entries, "mav0/imu0/sensor.yaml"))
    (imu_dir / "data.csv").write_bytes(_extract(EUROC_ZIP_URL, entries, "mav0/imu0/data.csv"))

    timestamps: list[int] = []
    for name in chosen:
        timestamp = Path(name).stem
        timestamps.append(int(timestamp))
        for channel in (0, 1):
            png = _extract(EUROC_ZIP_URL, entries, f"mav0/cam{channel}/data/{timestamp}.png")
            with Image.open(io.BytesIO(png)) as frame:
                frame.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT)).convert("L").save(
                    output / "mav0" / f"cam{channel}" / "data" / f"{timestamp}.jpg",
                    format="JPEG",
                    quality=JPEG_QUALITY,
                )
    manifest = {
        "sequence": "EuRoC MAV V1_01_easy (vicon_room_1)",
        "official_url": EUROC_OFFICIAL_URL,
        "mirror_url": EUROC_ZIP_URL,
        "zip_size_bytes": EUROC_ZIP_SIZE,
        "frame_start_index": FRAME_START,
        "frame_count": FRAME_COUNT,
        "frame_timestamps_ns": timestamps,
        "image_width": OUTPUT_WIDTH,
        "image_height": OUTPUT_HEIGHT,
        "rtabmap_image": image,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def prepare(
    output: Path,
    *,
    skip_docker: bool = False,
    image: str = PINNED_RTABMAP_IMAGE,
    from_upstream: bool = False,
) -> Path:
    if not skip_docker:
        _pull_image(image)
    if from_upstream:
        _prepare_from_upstream(output, image)
    else:
        _fetch_asset(output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--image", default=PINNED_RTABMAP_IMAGE)
    parser.add_argument("--skip-docker", action="store_true", help="do not pull the sidecar image")
    parser.add_argument(
        "--from-upstream",
        action="store_true",
        help="cut the subset from the upstream EuRoC zip instead of the release asset",
    )
    args = parser.parse_args(argv)
    output = prepare(
        args.output,
        skip_docker=args.skip_docker,
        image=args.image,
        from_upstream=args.from_upstream,
    )
    print(f"EuRoC subset and RTAB-Map sidecar prepared under {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
