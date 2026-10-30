"""NTU VIRAL outdoor drone scene: a ROS 1 stereo bag prepared into the EuRoC layout."""

import io
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from rosbags.rosbag1 import Writer
from rosbags.typesys import Stores, get_typestore

from surmap.demo.datasets import (
    DATASETS,
    CameraCalibration,
    DatasetSpec,
    PreparedDataset,
    PrepareProgress,
    Ros1Stereo,
    ensure_dataset,
    load_calibration,
)

TYPESTORE = get_typestore(Stores.ROS1_NOETIC)
IMAGE = TYPESTORE.types["sensor_msgs/msg/Image"]
HEADER = TYPESTORE.types["std_msgs/msg/Header"]
TIME = TYPESTORE.types["builtin_interfaces/msg/Time"]

T0_NS = 1_600_000_000_000_000_000
LEFT = CameraCalibration(
    intrinsics=(425.0, 426.8, 386.0, 241.9),
    distortion=(-0.288, 0.0746, 0.00078, -0.00023),
    resolution=(752, 480),
    t_bs=(0, 0, 1, 0.0055, 1, 0, 0, -0.1243, 0, 1, 0, 0.0161, 0, 0, 0, 1),
)
RIGHT = CameraCalibration(
    intrinsics=(431.3, 432.8, 354.9, 232.6),
    distortion=(-0.300, 0.0905, 0.00003, 0.00009),
    resolution=(752, 480),
    t_bs=(0, 0, 1, 0.0052, 1, 0, 0, 0.1348, 0, 1, 0, 0.0147, 0, 0, 0, 1),
)


def _image(t_ns: int, shade: int) -> bytes:
    pixels = np.full((4, 6), shade, dtype=np.uint8)
    message = IMAGE(
        header=HEADER(
            seq=0,
            stamp=TIME(sec=t_ns // 1_000_000_000, nanosec=t_ns % 1_000_000_000),
            frame_id="camera",
        ),
        height=4,
        width=6,
        encoding="mono8",
        is_bigendian=0,
        step=6,
        data=pixels.reshape(-1),
    )
    return bytes(TYPESTORE.serialize_ros1(message, IMAGE.__msgtype__))


def _flight_zip(path: Path, right_offsets_ms: tuple[int, ...] = (2, 3)) -> None:
    """A two-pair flight: right images a few ms after each left, plus LiDAR-like noise."""
    bag = path.parent / "flight.bag"
    with Writer(bag) as writer:
        left = writer.add_connection("/left/image_raw", IMAGE.__msgtype__, typestore=TYPESTORE)
        right = writer.add_connection("/right/image_raw", IMAGE.__msgtype__, typestore=TYPESTORE)
        other = writer.add_connection(
            "/os1_cloud_node1/image", IMAGE.__msgtype__, typestore=TYPESTORE
        )
        for index, offset_ms in enumerate(right_offsets_ms):
            t_left = T0_NS + index * 100_000_000
            t_right = t_left + offset_ms * 1_000_000
            writer.write(left, t_left, _image(t_left, 10 * index))
            writer.write(right, t_right, _image(t_right, 10 * index + 1))
            writer.write(other, t_left, _image(t_left, 255))
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(bag, "sbs_01/sbs_01.bag")
    bag.unlink()


def a_drone_flight(tmp_path: Path, right_offsets_ms: tuple[int, ...] = (2, 3)) -> DatasetSpec:
    zip_path = tmp_path / "flight.zip"
    _flight_zip(zip_path, right_offsets_ms)
    import hashlib

    data = zip_path.read_bytes()
    return DatasetSpec(
        dataset_id="ntu-tiny",
        title="NTU tiny",
        description="two outdoor drone frames",
        zip_url=zip_path.as_uri(),
        zip_size_bytes=len(data),
        zip_sha256=hashlib.sha256(data).hexdigest(),
        official_url="https://ntu-aris.github.io/ntu_viral_dataset/",
        dataset_format="ros1-stereo",
        ros1_stereo=Ros1Stereo("/left/image_raw", "/right/image_raw", LEFT, RIGHT),
        fps=10.0,
    )


def prepare(spec: DatasetSpec, cache: Path) -> PreparedDataset:
    return ensure_dataset(spec, cache, log=lambda _: None)


def pixels(path: Path) -> list[list[int]]:
    with Image.open(io.BytesIO(path.read_bytes())) as image:
        values: list[list[int]] = np.asarray(image).tolist()
        return values


def test_a_drone_flight_prepares_into_stereo_pairs_named_by_left_time(tmp_path: Path) -> None:
    # Given a flight whose right images land 2-3 ms after each left image
    spec = a_drone_flight(tmp_path)

    # When it is prepared
    prepared = prepare(spec, tmp_path / "cache")

    # Then each pair is named by the left time and holds both images' pixels
    second = T0_NS + 100_000_000
    assert prepared.timestamps_ns == (T0_NS, second)
    assert pixels(prepared.frame_path(0, second)) == [[10] * 6] * 4
    assert pixels(prepared.frame_path(1, second)) == [[11] * 6] * 4


def test_a_right_image_too_far_from_its_left_is_not_paired(tmp_path: Path) -> None:
    # Given a flight whose second right image trails its left by 40 ms
    spec = a_drone_flight(tmp_path, right_offsets_ms=(2, 40))

    # When it is prepared
    prepared = prepare(spec, tmp_path / "cache")

    # Then only the synchronised pair is kept
    assert prepared.timestamps_ns == (T0_NS,)


def test_the_flight_calibration_becomes_the_stereo_calibration(tmp_path: Path) -> None:
    # Given / When a flight is prepared with the authors' calibration
    prepared = prepare(a_drone_flight(tmp_path), tmp_path / "cache")
    calibration = load_calibration(prepared)

    # Then the left camera's intrinsics and the cameras' separation are used
    assert (calibration.fx, calibration.cx, calibration.width) == (425.0, 386.0, 752)
    assert abs(calibration.baseline_m - 0.25911) < 1e-4
    assert "distortion_coefficients: [-0.288, 0.0746, 0.00078, -0.00023]" in (
        prepared.sensor_yaml("cam0")
    )


def test_the_unpacked_bag_does_not_stay_in_the_cache(tmp_path: Path) -> None:
    # Given / When a flight is prepared
    prepared = prepare(a_drone_flight(tmp_path), tmp_path / "cache")

    # Then only the converted frames remain, not the multi-GB bag
    assert not list((tmp_path / "cache").rglob("*.bag"))
    assert {p.parent.parent.name for p in prepared.root.rglob("*.png")} == {"cam0", "cam1"}


def test_preparing_a_flight_reports_unpacking_then_converted_frames(tmp_path: Path) -> None:
    # Given a flight not yet in the cache
    spec = a_drone_flight(tmp_path)
    reports: list[PrepareProgress] = []

    # When it is prepared with a progress listener
    ensure_dataset(spec, tmp_path / "cache", log=lambda _: None, progress=reports.append)

    # Then the bag's unpacking is reported in bytes and conversion per image
    unpacking = [r for r in reports if r.phase == "unpacking"]
    assert unpacking and unpacking[-1].done == unpacking[-1].total > 0
    extracting = [r for r in reports if r.phase == "extracting"]
    assert extracting[-1].done == extracting[-1].total == 4  # 2 left + 2 right
    assert reports[-1].phase == "ready"


def test_the_registry_offers_an_outdoor_drone_flight() -> None:
    # Given / When the NTU VIRAL entry is read
    spec = DATASETS["ntu-viral-sbs-01"]

    # Then it is the sbs_01 plaza flight, pinned, with the authors'
    # calibration — the stereo left being the camera recorded on
    # /right/image_raw (measured: tracking holds only that way round)
    assert spec.dataset_format == "ros1-stereo"
    assert spec.zip_url.endswith("/sequences/sbs_01.zip")
    assert spec.zip_sha256 == "16063577be7b0d8b6ca89e40cf3ec45d603469048e7d989d25bab88f3950c390"
    assert spec.ros1_stereo is not None
    assert spec.ros1_stereo.left_topic == "/right/image_raw"
    assert spec.ros1_stereo.left.intrinsics[0] == 431.3364265799752
    assert spec.ros1_stereo.right.intrinsics[0] == 425.0258563372763
    assert spec.fps == 10.0
    assert "NTU VIRAL" in spec.credit and "CC BY-NC-SA 4.0" in spec.credit


def test_a_drone_flight_streams_through_the_demo(tmp_path: Path) -> None:
    # Given a prepared flight, played without SLAM
    from surmap.demo.server import DemoPlayer

    prepared = prepare(a_drone_flight(tmp_path), tmp_path / "cache")

    # When / Then both pairs play
    kinds = [e.kind for e in DemoPlayer(prepared, with_rtabmap=False).events()]
    assert kinds.count("frame") == 2
