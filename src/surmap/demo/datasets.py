"""Demo dataset registry: downloadable, cached, recorded datasets.

Adding a demo dataset means adding one `DatasetSpec` to `DATASETS`
(no other code changes): the launcher downloads its zip once into
the cache, verifies size + SHA-256, extracts the stereo/calibration
files, and records a manifest. Later launches reuse the cache and
download nothing. Nothing is installed on the host; the only network
fetch is the dataset zip itself.

Cache layout (default `~/.cache/surmap/demo-datasets`, override with
the launcher's `--cache-dir` or `$SURMAP_DEMO_CACHE_DIR`):

    downloads/<dataset-id>.zip     the verified upstream zip
    <dataset-id>/mav0/...          extracted EuRoC-style dataset
    <dataset-id>/manifest.json     frame index + provenance marker
    <dataset-id>/display/          generated half-res frames (lazy)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Frames are played at half resolution: full-res EuRoC is 752x480,
# the demo canvas and the stereo reconstructor work at 376x240.
DISPLAY_WIDTH = 376
DISPLAY_HEIGHT = 240


@dataclass(frozen=True)
class ZipAsset:
    """One extra downloadable zip a dataset needs, pinned like the main one."""

    url: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class DatasetSpec:
    """One downloadable demo dataset (the registry entry)."""

    dataset_id: str
    title: str
    description: str
    zip_url: str
    zip_size_bytes: int
    zip_sha256: str
    official_url: str
    dataset_format: str = "euroc"
    calibration: ZipAsset | None = None
    display_size: tuple[int, int] = (DISPLAY_WIDTH, DISPLAY_HEIGHT)
    fps: float = 20.0
    # Overlay depth ramp (near, mid, far) and the keyframe depth cap, in m.
    depth_stops_m: tuple[float, float, float] = (1.0, 3.0, 6.0)
    max_map_depth_m: float = 6.0
    credit: str = ""


# The registry. The EuRoC zip is byte-identical between the official
# ASL host and the mirror below (SHA-256 pinned); the mirror is the
# fetch URL because the official host is unreachable from some
# networks, and the hash — not the host — is what is trusted.
DATASETS: dict[str, DatasetSpec] = {
    "euroc-v1-01-easy": DatasetSpec(
        dataset_id="euroc-v1-01-easy",
        title="EuRoC V1_01_easy",
        description="Vicon Room 1 MAV flight, 2,912 stereo pairs at 20 Hz.",
        zip_url="https://huggingface.co/datasets/pepijn223/euroc-mirror/resolve/main/V1_01_easy.zip",
        zip_size_bytes=1_149_702_102,
        zip_sha256="a920fe5b5e69a6ad19b32f1cfaf90ac2f59d45dfd1ca18cc9722e07684ba45fa",
        official_url=(
            "https://robotics.ethz.ch/~asl-datasets/ijrr_euroc_mav_dataset/"
            "vicon_room/vicon_room_1/V1_01_easy/V1_01_easy.zip"
        ),
    ),
}


def default_cache_dir() -> Path:
    override = os.environ.get("SURMAP_DEMO_CACHE_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".cache" / "surmap" / "demo-datasets"


@dataclass(frozen=True)
class PreparedDataset:
    spec: DatasetSpec
    root: Path
    timestamps_ns: tuple[int, ...]

    def frame_path(self, channel: int, t_ns: int) -> Path:
        return self.root / "mav0" / f"cam{channel}" / "data" / f"{t_ns}.png"

    def sensor_yaml(self, sensor: str) -> str:
        return (self.root / "mav0" / sensor / "sensor.yaml").read_text(encoding="utf-8")

    def imu_csv(self) -> str:
        path = self.root / "mav0" / "imu0" / "data.csv"
        return path.read_text(encoding="utf-8") if path.is_file() else ""


@dataclass(frozen=True)
class DemoCalibration:
    """Stereo calibration at one resolution, from EuRoC sensor.yaml."""

    fx: float
    fy: float
    cx: float
    cy: float
    baseline_m: float
    width: int
    height: int

    def scaled(self, width: int, height: int) -> DemoCalibration:
        factor_x = width / self.width
        factor_y = height / self.height
        return DemoCalibration(
            fx=self.fx * factor_x,
            fy=self.fy * factor_y,
            cx=self.cx * factor_x,
            cy=self.cy * factor_y,
            baseline_m=self.baseline_m,
            width=width,
            height=height,
        )


def scaled_sensor_yaml(text: str, width: int, height: int) -> str:
    """A EuRoC `sensor.yaml` rewritten for `width`x`height` frames."""
    source = re.search(r"resolution: \[(\d+), (\d+)\]", text)
    if source is None:
        raise ValueError("sensor.yaml has no resolution")
    factor_x = width / int(source.group(1))
    factor_y = height / int(source.group(2))
    text = text.replace(source.group(0), f"resolution: [{width}, {height}]")

    def scale_intrinsics(match: re.Match[str]) -> str:
        fx, fy, cx, cy = (float(part) for part in match.group(1).split(","))
        return f"intrinsics: [{fx * factor_x}, {fy * factor_y}, {cx * factor_x}, {cy * factor_y}]"

    return re.sub(r"intrinsics: \[([^\]]+)\]", scale_intrinsics, text)


def load_calibration(prepared: PreparedDataset) -> DemoCalibration:
    """`DemoCalibration` at native resolution from cam0/cam1 yaml."""
    translations: list[tuple[float, float, float]] = []
    intrinsics: list[float] = []
    resolution: list[int] = []
    for channel in (0, 1):
        text = prepared.sensor_yaml(f"cam{channel}")
        data_match = re.search(r"data: \[([^\]]+)\]", text)
        intrinsics_match = re.search(r"intrinsics: \[([^\]]+)\]", text)
        resolution_match = re.search(r"resolution: \[(\d+), (\d+)\]", text)
        if data_match is None or intrinsics_match is None or resolution_match is None:
            raise ValueError(f"cam{channel}/sensor.yaml is missing calibration fields")
        data = [float(value) for value in data_match.group(1).split(",")]
        translations.append((data[3], data[7], data[11]))
        if channel == 0:
            intrinsics = [float(value) for value in intrinsics_match.group(1).split(",")]
            resolution = [int(resolution_match.group(1)), int(resolution_match.group(2))]
    return DemoCalibration(
        fx=intrinsics[0],
        fy=intrinsics[1],
        cx=intrinsics[2],
        cy=intrinsics[3],
        baseline_m=math.dist(translations[0], translations[1]),
        width=resolution[0],
        height=resolution[1],
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path, log: Callable[[str], None]) -> None:
    partial = target.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        last_report = -1
        for chunk in iter(lambda: response.read(1 << 20), b""):
            out.write(chunk)
            done += len(chunk)
            percent = done * 100 // total if total else 0
            if percent >= last_report + 10:
                last_report = percent
                log(f"  downloaded {done / 1e9:.2f} GB ({percent}%)")
    partial.replace(target)


def _extract(spec: DatasetSpec, zip_path: Path, root: Path) -> None:
    wanted_prefixes = ("mav0/cam0/", "mav0/cam1/", "mav0/imu0/")
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir() or not member.filename.startswith(wanted_prefixes):
                continue
            target = root / member.filename
            if not target.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"unsafe zip member: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out, length=1 << 20)


def ensure_dataset(
    spec: DatasetSpec,
    cache_dir: Path,
    *,
    log: Callable[[str], None] = print,
    fetch: Callable[[str, Path], None] | None = None,
) -> PreparedDataset:
    """Download (once), verify, extract, and index `spec` in the cache."""
    if spec.dataset_format != "euroc":
        raise ValueError(f"unsupported dataset format: {spec.dataset_format}")
    root = cache_dir / spec.dataset_id
    manifest_path = root / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        timestamps = tuple(int(value) for value in manifest["frame_timestamps_ns"])
        if timestamps:
            log(f"dataset {spec.dataset_id}: cache hit ({len(timestamps)} pairs)")
            return PreparedDataset(spec, root, timestamps)

    downloads = cache_dir / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    zip_path = downloads / f"{spec.dataset_id}.zip"
    if zip_path.is_file() and zip_path.stat().st_size == spec.zip_size_bytes:
        log(f"dataset {spec.dataset_id}: zip cached, verifying…")
    else:
        log(f"dataset {spec.dataset_id}: downloading {spec.title}")
        log(f"  size: {spec.zip_size_bytes / 1e9:.2f} GB")
        log(f"  source: {spec.zip_url}")
        log(f"  official: {spec.official_url}")
        (fetch or (lambda url, target: _download(url, target, log)))(spec.zip_url, zip_path)
    if zip_path.stat().st_size != spec.zip_size_bytes:
        raise ValueError(f"{zip_path} has the wrong size; refusing to use it")
    if _sha256(zip_path) != spec.zip_sha256:
        raise ValueError(f"{zip_path} failed SHA-256 verification; refusing to use it")

    log(f"dataset {spec.dataset_id}: extracting stereo frames…")
    root.mkdir(parents=True, exist_ok=True)
    _extract(spec, zip_path, root)
    cam0 = sorted((root / "mav0" / "cam0" / "data").glob("*.png"))
    cam1_names = {path.name for path in (root / "mav0" / "cam1" / "data").glob("*.png")}
    timestamps = tuple(int(path.stem) for path in cam0 if path.name in cam1_names)
    if not timestamps:
        raise ValueError(f"no stereo pairs extracted for {spec.dataset_id}")
    manifest = {
        "dataset_id": spec.dataset_id,
        "title": spec.title,
        "zip_url": spec.zip_url,
        "official_url": spec.official_url,
        "zip_sha256": spec.zip_sha256,
        "frame_count": len(timestamps),
        "frame_timestamps_ns": list(timestamps),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"dataset {spec.dataset_id}: ready ({len(timestamps)} pairs)")
    return PreparedDataset(spec, root, timestamps)
