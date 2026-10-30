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

import bisect
import calendar
import hashlib
import json
import math
import os
import re
import shutil
import time
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from rosbags.rosbag1 import Reader
from rosbags.typesys import Stores, get_typestore

# Frames are played at half resolution: full-res EuRoC is 752x480,
# the demo canvas and the stereo reconstructor work at 376x240.
DISPLAY_WIDTH = 376
DISPLAY_HEIGHT = 240


@dataclass(frozen=True)
class PrepareProgress:
    """One step of preparing a scene: `downloading` (bytes), `verifying`,
    `extracting` (files) or `ready`."""

    phase: str
    done: int
    total: int


Report = Callable[[PrepareProgress], None]


def _no_report(_: PrepareProgress) -> None:
    pass


@dataclass(frozen=True)
class ZipAsset:
    """One extra downloadable zip a dataset needs, pinned like the main one."""

    url: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class CameraCalibration:
    """One camera as EuRoC's sensor.yaml describes it (pinhole, radial-tangential)."""

    intrinsics: tuple[float, float, float, float]  # fx, fy, cx, cy
    distortion: tuple[float, float, float, float]  # k1, k2, p1, p2
    resolution: tuple[int, int]
    t_bs: tuple[float, ...]  # body <- sensor, 4x4 row-major


@dataclass(frozen=True)
class Ros1Stereo:
    """Where a ROS 1 bag keeps its stereo pair, and that pair's calibration."""

    left_topic: str
    right_topic: str
    left: CameraCalibration
    right: CameraCalibration
    # A right image pairs with the left image at most this far from it.
    max_pair_skew_ns: int = 5_000_000


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
    ros1_stereo: Ros1Stereo | None = None
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
    # KITTI raw, fetched from KITTI's own host and converted locally; never
    # re-hosted (CC BY-NC-SA 3.0, academic use — credited on the page).
    "kitti-2011-09-26-drive-0009": DatasetSpec(
        dataset_id="kitti-2011-09-26-drive-0009",
        title="KITTI 2011_09_26 drive 0009",
        description="Karlsruhe city drive, 447 rectified grey stereo pairs at 10 Hz.",
        zip_url=(
            "https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/"
            "2011_09_26_drive_0009/2011_09_26_drive_0009_sync.zip"
        ),
        zip_size_bytes=1_791_264_044,
        zip_sha256="909639de40540f1d9bd8e3c181d79556ee4852781aa4684999f4cda3f3ef2611",
        official_url="https://www.cvlibs.net/datasets/kitti/raw_data.php",
        dataset_format="kitti-raw",
        calibration=ZipAsset(
            url="https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_26_calib.zip",
            size_bytes=4_068,
            sha256="e0108cfd000cf802c14ed94fba38601185c792e5640abba015a34b7a85b812e0",
        ),
        # Half of the rectified 1242x375; a 0.54 m baseline maps a street.
        display_size=(620, 188),
        fps=10.0,
        depth_stops_m=(5.0, 15.0, 40.0),
        max_map_depth_m=30.0,
        credit=(
            "KITTI raw data, Geiger, Lenz, Stiller and Urtasun (KIT and Toyota Technological "
            "Institute), CC BY-NC-SA 3.0, for academic use — cvlibs.net/datasets/kitti"
        ),
    ),
    # NTU VIRAL, a UAV flight over a campus plaza: the ROS 1 bag is read
    # once into the EuRoC layout. The zip has no calibration; it is the
    # dataset authors' own (brytsknguyen/VINS-Fusion@3d8bf9e,
    # config/ntuviral: camLeft.yaml, camRight.yaml, body_T_cam1/cam0).
    "ntu-viral-sbs-01": DatasetSpec(
        dataset_id="ntu-viral-sbs-01",
        title="NTU VIRAL sbs_01",
        description="Drone flight over NTU's Biological Sciences plaza, 10 Hz stereo.",
        zip_url=(
            "https://huggingface.co/datasets/Yuan-Shenghai/NTU-VIRAL-DATASET/"
            "resolve/main/sequences/sbs_01.zip"
        ),
        zip_size_bytes=3_775_725_925,
        zip_sha256="16063577be7b0d8b6ca89e40cf3ec45d603469048e7d989d25bab88f3950c390",
        official_url="https://ntu-aris.github.io/ntu_viral_dataset/",
        dataset_format="ros1-stereo",
        # Intrinsics: the dataset authors' (VINS-Fusion config). Extrinsics:
        # NOT that config's body_T_cam (an initial guess there, which puts
        # the rig the wrong way round: 95-97 % negative disparity on real
        # pairs), but cv2.stereoCalibrate on the authors' own checkerboard
        # pairs (calibration/calib_stereo.zip: 132 pairs, 9x6 at 80 mm,
        # intrinsics fixed, RMS 0.359 px): right camera 0.2593 m along +x
        # of the left, rotated 1.16 deg; 93-99 % positive disparity.
        ros1_stereo=Ros1Stereo(
            left_topic="/left/image_raw",
            right_topic="/right/image_raw",
            left=CameraCalibration(
                intrinsics=(
                    425.0258563372763,
                    426.7976260903337,
                    386.015186655088,
                    241.913033674344,
                ),
                distortion=(
                    -0.288105327549552,
                    0.074578284234601,
                    7.784489598138802e-04,
                    -2.277853975035461e-04,
                ),
                resolution=(752, 480),
                # The left camera is the body frame.
                t_bs=(
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                ),
            ),
            right=CameraCalibration(
                intrinsics=(
                    431.3364265799752,
                    432.7527965378035,
                    354.8956286992647,
                    232.5508916495161,
                ),
                distortion=(
                    -0.300267420221178,
                    0.090544063693053,
                    3.330220891093334e-05,
                    8.989607188457415e-05,
                ),
                resolution=(752, 480),
                t_bs=(
                    0.9997985489,
                    0.0095333317,
                    0.0176628787,
                    0.2593142767,
                    -0.0095845646,
                    0.9999500957,
                    0.0028182124,
                    -0.000876373,
                    -0.0176351303,
                    -0.0029869357,
                    0.9998400274,
                    0.0006552279,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                ),
            ),
        ),
        fps=10.0,
        # 0.26 m baseline at 376 px wide: fx·b ≈ 55 px·m, so maps to 20 m.
        depth_stops_m=(3.0, 8.0, 20.0),
        max_map_depth_m=20.0,
        credit=(
            "NTU VIRAL dataset, Nguyen, Yuan, Cao, Yang, Nguyen and Xie (NTU Singapore), "
            "CC BY-NC-SA 4.0, for non-commercial use — ntu-aris.github.io/ntu_viral_dataset"
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

    @property
    def has_imu(self) -> bool:
        return (self.root / "mav0" / "imu0" / "sensor.yaml").is_file()

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


def _download(
    url: str, target: Path, log: Callable[[str], None], report: Report = _no_report
) -> None:
    partial = target.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        last_report = -1
        report(PrepareProgress("downloading", 0, total))
        for chunk in iter(lambda: response.read(1 << 20), b""):
            out.write(chunk)
            done += len(chunk)
            report(PrepareProgress("downloading", done, total))
            percent = done * 100 // total if total else 0
            if percent >= last_report + 10:
                last_report = percent
                log(f"  downloaded {done / 1e9:.2f} GB ({percent}%)")
    partial.replace(target)


def _extract(zip_path: Path, root: Path, report: Report = _no_report) -> None:
    wanted_prefixes = ("mav0/cam0/", "mav0/cam1/", "mav0/imu0/")
    with zipfile.ZipFile(zip_path) as archive:
        wanted = [
            member
            for member in archive.infolist()
            if not member.is_dir() and member.filename.startswith(wanted_prefixes)
        ]
        for index, member in enumerate(wanted, start=1):
            report(PrepareProgress("extracting", index, len(wanted)))
            target = root / member.filename
            if not target.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"unsafe zip member: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out, length=1 << 20)


def _kitti_t_ns(stamp: str) -> int:
    """A KITTI timestamp line ("2011-09-26 13:02:44.329372928") in ns, read as UTC."""
    whole, _, fraction = stamp.strip().partition(".")
    seconds = calendar.timegm(time.strptime(whole, "%Y-%m-%d %H:%M:%S"))
    return seconds * 1_000_000_000 + int(fraction.ljust(9, "0")[:9])


def _kitti_projection(calib: str, camera: str) -> tuple[list[float], list[int]]:
    """(P_rect 3x4 row-major, S_rect [w, h]) of one rectified camera."""
    rows = dict(line.split(":", 1) for line in calib.splitlines() if ":" in line)
    projection = [float(value) for value in rows[f"P_rect_{camera}"].split()]
    size = [round(float(value)) for value in rows[f"S_rect_{camera}"].split()]
    return projection, size


def _kitti_sensor_yaml(projection: list[float], size: list[int], x_m: float) -> str:
    """EuRoC sensor.yaml for a rectified KITTI camera `x_m` right of cam0."""
    fx, cx, fy, cy = projection[0], projection[2], projection[5], projection[6]
    return (
        "sensor_type: camera\n"
        "T_BS:\n  cols: 4\n  rows: 4\n"
        f"  data: [1.0, 0.0, 0.0, {x_m!r},\n"
        "         0.0, 1.0, 0.0, 0.0,\n"
        "         0.0, 0.0, 1.0, 0.0,\n"
        "         0.0, 0.0, 0.0, 1.0]\n"
        "rate_hz: 10\n"
        f"resolution: [{size[0]}, {size[1]}]\n"
        "camera_model: pinhole\n"
        f"intrinsics: [{fx!r}, {fy!r}, {cx!r}, {cy!r}]\n"
        "distortion_model: radial-tangential\n"
        "distortion_coefficients: [0.0, 0.0, 0.0, 0.0]\n"
    )


def _extract_kitti_raw(
    zip_path: Path, calibration_path: Path, root: Path, report: Report = _no_report
) -> None:
    """A KITTI raw `_sync` drive as the EuRoC layout: grey stereo + calibration.

    KITTI sync frames are rectified and aligned by index, so cam0's
    timestamps name both images of a pair.
    """
    with zipfile.ZipFile(calibration_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("calib_cam_to_cam.txt"))
        calib = archive.read(name).decode()
    left, left_size = _kitti_projection(calib, "00")
    right, right_size = _kitti_projection(calib, "01")
    baseline_m = -right[3] / right[0]
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        stamps_name = next(n for n in names if n.endswith("image_00/timestamps.txt"))
        drive = stamps_name.removesuffix("image_00/timestamps.txt")
        stamps = [
            _kitti_t_ns(line) for line in archive.read(stamps_name).decode().splitlines() if line
        ]
        for channel, (projection, size, x_m) in enumerate(
            ((left, left_size, 0.0), (right, right_size, baseline_m))
        ):
            camera = root / "mav0" / f"cam{channel}"
            (camera / "data").mkdir(parents=True, exist_ok=True)
            (camera / "sensor.yaml").write_text(
                _kitti_sensor_yaml(projection, size, x_m), encoding="utf-8"
            )
            for index, t_ns in enumerate(stamps):
                member = f"{drive}image_0{channel}/data/{index:010d}.png"
                if member in names:
                    (camera / "data" / f"{t_ns}.png").write_bytes(archive.read(member))
                report(
                    PrepareProgress(
                        "extracting", channel * len(stamps) + index + 1, 2 * len(stamps)
                    )
                )


class _RosStamp(Protocol):
    sec: int
    nanosec: int


class _RosHeader(Protocol):
    stamp: _RosStamp


class _RosImage(Protocol):
    """The `sensor_msgs/Image` fields read here (rosbags deserialises to `object`)."""

    header: _RosHeader
    height: int
    width: int
    encoding: str
    step: int
    data: NDArray[np.uint8]


def _ros_image_gray(message: object) -> tuple[int, NDArray[np.uint8]]:
    """(stamp ns, H x W 8-bit grey pixels) of one `sensor_msgs/Image`."""
    image = cast(_RosImage, message)
    rows = np.asarray(image.data, dtype=np.uint8).reshape(image.height, image.step)
    if image.encoding in ("mono8", "8UC1"):
        pixels = rows[:, : image.width]
    elif image.encoding in ("mono16", "16UC1"):
        wide = rows[:, : 2 * image.width].view("<u2" if not _big_endian(message) else ">u2")
        pixels = (wide >> 8).astype(np.uint8)
    else:
        raise ValueError(f"unsupported image encoding {image.encoding!r}")
    stamp = image.header.stamp
    return stamp.sec * 1_000_000_000 + stamp.nanosec, np.ascontiguousarray(pixels)


def _big_endian(message: object) -> bool:
    return bool(getattr(message, "is_bigendian", 0))


def _euroc_sensor_yaml(camera: CameraCalibration, rate_hz: float) -> str:
    """EuRoC `sensor.yaml` for one pinhole, radial-tangential camera."""
    rows = [", ".join(repr(float(v)) for v in camera.t_bs[i : i + 4]) for i in range(0, 16, 4)]
    data = ",\n         ".join(rows)
    return (
        "sensor_type: camera\n"
        f"T_BS:\n  cols: 4\n  rows: 4\n  data: [{data}]\n"
        f"rate_hz: {rate_hz:g}\n"
        f"resolution: [{camera.resolution[0]}, {camera.resolution[1]}]\n"
        "camera_model: pinhole\n"
        f"intrinsics: [{', '.join(repr(float(v)) for v in camera.intrinsics)}]\n"
        "distortion_model: radial-tangential\n"
        f"distortion_coefficients: [{', '.join(repr(float(v)) for v in camera.distortion)}]\n"
    )


def _unpack_bag(zip_path: Path, target: Path, report: Report) -> None:
    """The zip's ROS 1 bag, copied out so it can be read with seeks."""
    with zipfile.ZipFile(zip_path) as archive:
        member = next((m for m in archive.infolist() if m.filename.endswith(".bag")), None)
        if member is None:
            raise ValueError(f"{zip_path} holds no .bag file")
        done = 0
        with archive.open(member) as source, target.open("wb") as out:
            for chunk in iter(lambda: source.read(1 << 22), b""):
                out.write(chunk)
                done += len(chunk)
                report(PrepareProgress("unpacking", done, member.file_size))


def _extract_ros1_stereo(
    zip_path: Path, root: Path, stereo: Ros1Stereo, fps: float, report: Report = _no_report
) -> None:
    """A ROS 1 stereo bag as the EuRoC layout.

    Each image is written as it is read (memory stays flat); right images
    are then paired with the nearest left image within the skew and
    renamed to the left stamp, as EuRoC pairs share a name. The unpacked
    bag is deleted afterwards — only the frames stay in the cache.
    """
    left_dir, right_dir = root / "mav0" / "cam0" / "data", root / "mav0" / "cam1" / "data"
    staging = root / "mav0" / "cam1" / "staging"
    for folder in (left_dir, right_dir, staging):
        folder.mkdir(parents=True, exist_ok=True)
    for channel, camera in ((0, stereo.left), (1, stereo.right)):
        (root / "mav0" / f"cam{channel}" / "sensor.yaml").write_text(
            _euroc_sensor_yaml(camera, fps), encoding="utf-8"
        )
    bag = root / "unpacking.bag"
    try:
        _unpack_bag(zip_path, bag, report)
        lefts: list[int] = []
        rights: list[int] = []
        typestore = get_typestore(Stores.ROS1_NOETIC)
        with Reader(bag) as reader:
            wanted = [
                c for c in reader.connections if c.topic in (stereo.left_topic, stereo.right_topic)
            ]
            total = sum(c.msgcount for c in wanted)
            for index, (connection, _, raw) in enumerate(reader.messages(connections=wanted)):
                t_ns, pixels = _ros_image_gray(typestore.deserialize_ros1(raw, connection.msgtype))
                is_left = connection.topic == stereo.left_topic
                folder = left_dir if is_left else staging
                Image.fromarray(pixels).save(folder / f"{t_ns}.png", compress_level=1)
                (lefts if is_left else rights).append(t_ns)
                report(PrepareProgress("extracting", index + 1, total))
    finally:
        bag.unlink(missing_ok=True)
    lefts.sort()
    taken: set[int] = set()
    for t_right in sorted(rights):
        at = bisect.bisect_left(lefts, t_right)
        near = [lefts[i] for i in (at - 1, at) if 0 <= i < len(lefts)]
        t_left = min(near, key=lambda t: abs(t - t_right), default=None)
        source = staging / f"{t_right}.png"
        if t_left is None or t_left in taken or abs(t_left - t_right) > stereo.max_pair_skew_ns:
            source.unlink()
            continue
        taken.add(t_left)
        source.replace(right_dir / f"{t_left}.png")
    staging.rmdir()
    for t_left in lefts:
        if t_left not in taken:
            (left_dir / f"{t_left}.png").unlink()


def _fetch_verified(
    url: str,
    size_bytes: int,
    sha256: str,
    target: Path,
    log: Callable[[str], None],
    fetch: Callable[[str, Path], None] | None,
    report: Report = _no_report,
) -> None:
    """`target` downloaded once from `url`, then size + SHA-256 checked."""
    if target.is_file() and target.stat().st_size == size_bytes:
        log(f"  {target.name} cached, verifying…")
    else:
        log(f"  fetching {url} ({size_bytes / 1e9:.2f} GB)")
        if fetch is None:
            _download(url, target, log, report)
        else:
            report(PrepareProgress("downloading", 0, size_bytes))
            fetch(url, target)
            report(PrepareProgress("downloading", size_bytes, size_bytes))
    report(PrepareProgress("verifying", 0, 1))
    if target.stat().st_size != size_bytes:
        raise ValueError(f"{target} has the wrong size; refusing to use it")
    if _sha256(target) != sha256:
        raise ValueError(f"{target} failed SHA-256 verification; refusing to use it")
    report(PrepareProgress("verifying", 1, 1))


def cached_dataset(spec: DatasetSpec, cache_dir: Path) -> PreparedDataset | None:
    """`spec` as already prepared in the cache, or None; never downloads."""
    root = cache_dir / spec.dataset_id
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    timestamps = tuple(int(value) for value in manifest["frame_timestamps_ns"])
    return PreparedDataset(spec, root, timestamps) if timestamps else None


def ensure_dataset(
    spec: DatasetSpec,
    cache_dir: Path,
    *,
    log: Callable[[str], None] = print,
    fetch: Callable[[str, Path], None] | None = None,
    progress: Callable[[PrepareProgress], None] | None = None,
) -> PreparedDataset:
    """Download (once), verify, extract, and index `spec` in the cache."""
    if spec.dataset_format not in ("euroc", "kitti-raw", "ros1-stereo"):
        raise ValueError(f"unsupported dataset format: {spec.dataset_format}")
    report = progress or _no_report
    cached = cached_dataset(spec, cache_dir)
    if cached is not None:
        log(f"dataset {spec.dataset_id}: cache hit ({len(cached.timestamps_ns)} pairs)")
        report(PrepareProgress("ready", 1, 1))
        return cached
    root = cache_dir / spec.dataset_id
    manifest_path = root / "manifest.json"

    downloads = cache_dir / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    zip_path = downloads / f"{spec.dataset_id}.zip"
    log(f"dataset {spec.dataset_id}: {spec.title} (official: {spec.official_url})")
    _fetch_verified(
        spec.zip_url, spec.zip_size_bytes, spec.zip_sha256, zip_path, log, fetch, report
    )

    log(f"dataset {spec.dataset_id}: extracting stereo frames…")
    root.mkdir(parents=True, exist_ok=True)
    if spec.dataset_format == "kitti-raw":
        if spec.calibration is None:
            raise ValueError(f"{spec.dataset_id}: a kitti-raw dataset needs its calibration zip")
        calibration_path = downloads / f"{spec.dataset_id}-calibration.zip"
        _fetch_verified(
            spec.calibration.url,
            spec.calibration.size_bytes,
            spec.calibration.sha256,
            calibration_path,
            log,
            fetch,
            report,
        )
        _extract_kitti_raw(zip_path, calibration_path, root, report)
    elif spec.dataset_format == "ros1-stereo":
        if spec.ros1_stereo is None:
            raise ValueError(f"{spec.dataset_id}: a ros1-stereo dataset needs its topics")
        _extract_ros1_stereo(zip_path, root, spec.ros1_stereo, spec.fps, report)
    else:
        _extract(zip_path, root, report)
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
    report(PrepareProgress("ready", 1, 1))
    return PreparedDataset(spec, root, timestamps)
