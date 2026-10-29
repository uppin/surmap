"""Demo + SAM 2.1 tests: Coral boxes prompt SAM live, RTAB-Map keyframes
are segmented into a semantic map layer after the map is built.

Seams faked: the detection source (Coral), the box segmenter (SAM),
the stereo reconstructor and the batch SLAM backend (RTAB-Map
sidecar). The player, its SAM worker and the fusion are real.
"""

import hashlib
import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from surmap.demo.datasets import DatasetSpec, PreparedDataset, ensure_dataset
from surmap.demo.server import DemoEvent, DemoPlayer
from surmap.detection.tracker import TrackedDetection
from surmap.slam.base import FrameResult
from surmap.survey.sam import SamDetection
from surmap.survey.sam2 import BoxPrompt, Sam2Segment
from surmap.survey.stereo import FrameImage, StereoRig
from surmap.types import Pose, StereoFramePair, Vec3

EUROC_MOUNT_CAMERA_YAML = """sensor_type: camera
T_BS:
  cols: 4
  rows: 4
  data: [0.0, -1.0, 0.0, 0.0,
         1.0, 0.0, 0.0, -0.05,
         0.0, 0.0, 1.0, 0.0,
         0.0, 0.0, 0.0, 1.0]
rate_hz: 20
resolution: [752, 480]
camera_model: pinhole
intrinsics: [458.0, 457.0, 367.0, 248.0]
distortion_model: radial-tangential
distortion_coefficients: [0.0, 0.0, 0.0, 0.0]
"""


def two_pair_dataset(tmp_path: Path) -> PreparedDataset:
    buffer = io.BytesIO()
    Image.new("L", (752, 480), 90).save(buffer, format="PNG")
    zip_path = tmp_path / "two.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for t_ns in (100, 200):
            archive.writestr(f"mav0/cam0/data/{t_ns}.png", buffer.getvalue())
            archive.writestr(f"mav0/cam1/data/{t_ns}.png", buffer.getvalue())
        archive.writestr("mav0/cam0/sensor.yaml", EUROC_MOUNT_CAMERA_YAML)
        archive.writestr("mav0/cam1/sensor.yaml", EUROC_MOUNT_CAMERA_YAML.replace("-0.05", "0.06"))
        archive.writestr("mav0/imu0/sensor.yaml", "sensor_type: imu\n")
        archive.writestr("mav0/imu0/data.csv", "t,wx,wy,wz,ax,ay,az\n")
    data = zip_path.read_bytes()
    spec = DatasetSpec(
        dataset_id="two-pairs",
        title="Two Pairs",
        description="two pairs, EuRoC mount",
        zip_url="https://example.invalid/two.zip",
        zip_size_bytes=len(data),
        zip_sha256=hashlib.sha256(data).hexdigest(),
        official_url="https://example.invalid/",
    )

    def fetch(_url: str, target: Path) -> None:
        target.write_bytes(data)

    return ensure_dataset(spec, tmp_path / "cache", log=lambda _: None, fetch=fetch)


class CarEveryFrame:
    """Coral stand-in: one tracked car in every frame."""

    def detect_tracked(self, frame_id: int, rgb: NDArray[np.uint8]) -> tuple[TrackedDetection, ...]:
        return (TrackedDetection("car", 0.9, (10.0, 10.0, 200.0, 200.0), 7, frame_id),)


class NothingDetected:
    def detect_tracked(self, frame_id: int, rgb: NDArray[np.uint8]) -> tuple[TrackedDetection, ...]:
        return ()


class WholeFrameSegmenter:
    """SAM stand-in: every prompt's mask is the whole frame."""

    def __init__(self) -> None:
        self.calls: list[tuple[BoxPrompt, ...]] = []

    def segment(
        self, rgb: NDArray[np.uint8], prompts: tuple[BoxPrompt, ...]
    ) -> tuple[Sam2Segment, ...]:
        self.calls.append(prompts)
        mask = np.ones(rgb.shape[:2], dtype=bool)
        return tuple(
            Sam2Segment(
                SamDetection(
                    prompt.label,
                    0.95,
                    prompt.box_xyxy,
                    ((0.0, 0.0), (375.0, 0.0), (375.0, 239.0)),
                    prompt.track_id,
                ),
                mask,
            )
            for prompt in prompts
        )


class WallTwoMetresAhead:
    """Stereo stand-in: a flat wall of points 2 m in front of the camera."""

    def reconstruct(self, left: FrameImage, right: FrameImage, rig: StereoRig) -> tuple[Vec3, ...]:
        return tuple(Vec3(x * 0.1, y * 0.1, 2.0) for x in range(-3, 4) for y in range(-2, 3))


class OneKeyframeRtabmap:
    """Batch SLAM stand-in: frame 1 is a keyframe posed 10 m forward."""

    def __init__(self) -> None:
        self.closed = False

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        return FrameResult(frame.frame_id, frame.t_ns, None, ())

    def flush(self) -> list[FrameResult]:
        return [FrameResult(1, 100, Pose(Vec3(10.0, 0.0, 0.0)), (Vec3(11.0, 0.0, 0.0),))]

    def trajectory(self) -> list[Pose]:
        return [Pose(Vec3(10.0, 0.0, 0.0))]

    def close(self) -> None:
        self.closed = True


def kinds(events: list[DemoEvent]) -> list[str]:
    return [event.kind for event in events]


def test_coral_boxes_are_segmented_live_into_frame_keyed_segment_events(tmp_path: Path) -> None:
    # Given a player where Coral sees a car and SAM segments it
    player = DemoPlayer(
        two_pair_dataset(tmp_path),
        fps=50.0,
        with_rtabmap=False,
        detection_source=CarEveryFrame(),
        segmenter=WholeFrameSegmenter(),
    )

    # When the dataset plays
    events = list(player.events())

    # Then SAM's result arrives as its own event, keyed to a played frame
    segments = [event for event in events if event.kind == "segments"]
    assert segments
    assert segments[0].data["frame_id"] in (1, 2)
    objects = segments[0].data["objects"]
    assert isinstance(objects, list)
    assert objects[0]["label"] == "car"
    assert objects[0]["track_id"] == 7
    assert objects[0]["polygon"]


def test_frames_without_coral_boxes_are_never_offered_to_sam(tmp_path: Path) -> None:
    # Given a player where Coral detects nothing
    segmenter = WholeFrameSegmenter()
    player = DemoPlayer(
        two_pair_dataset(tmp_path),
        fps=50.0,
        with_rtabmap=False,
        detection_source=NothingDetected(),
        segmenter=segmenter,
    )

    # When the dataset plays
    events = list(player.events())

    # Then SAM never ran and no segment events were sent
    assert segmenter.calls == []
    assert "segments" not in kinds(events)


def test_rtabmap_keyframes_are_segmented_into_a_semantic_map_layer(tmp_path: Path) -> None:
    # Given RTAB-Map posing frame 1 at 10 m forward, a wall 2 m ahead,
    # and a car covering the frame
    rtabmap = OneKeyframeRtabmap()
    player = DemoPlayer(
        two_pair_dataset(tmp_path),
        fps=50.0,
        detection_source=CarEveryFrame(),
        segmenter=WholeFrameSegmenter(),
        stereo=WallTwoMetresAhead(),
        slam_backend=lambda: rtabmap,
    )

    # When the dataset plays and the map is built
    events = list(player.events())

    # Then the final map carries a car layer about 12 m forward
    final = events[-1]
    assert final.kind == "final"
    semantic = final.data["semantic"]
    assert isinstance(semantic, list)
    (car,) = semantic
    assert car["label"] == "car"
    assert car["count"] == 35
    assert all(abs(x - 12.0) < 0.01 for x, _y in car["xy"])
    assert rtabmap.closed


def test_sam_counts_are_reported_in_the_final_event(tmp_path: Path) -> None:
    # Given the same keyframe setup
    player = DemoPlayer(
        two_pair_dataset(tmp_path),
        fps=50.0,
        detection_source=CarEveryFrame(),
        segmenter=WholeFrameSegmenter(),
        stereo=WallTwoMetresAhead(),
        slam_backend=OneKeyframeRtabmap,
    )

    # When the dataset plays
    final = list(player.events())[-1]

    # Then one RTAB-Map keyframe was segmented
    sam = final.data["sam"]
    assert isinstance(sam, dict)
    assert sam["keyframes_segmented"] == 1


def test_sam_without_coral_prompts_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Coral"):
        DemoPlayer(
            two_pair_dataset(tmp_path),
            with_rtabmap=False,
            segmenter=WholeFrameSegmenter(),
        )
