"""Gazebo segmentation labels, pose matching, and bench export. No gz process."""

from __future__ import annotations

import argparse
import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, cast

from PIL import Image

from surmap.segbench.dataset import export_sitl_bench, load_bench
from surmap.simulation.gz_labels import label_for_model, label_sdf
from surmap.simulation.sitl_dump import (
    StampedPose,
    label_image_to_png,
    load_pose_jsonl,
    nearest_pose,
    pose_record,
)

_MODEL = Path("docs/simulation/gz/surmap_stereo_cam/model.sdf")
_WORLD = Path("docs/simulation/gz/worlds/disaster_block.sdf")


def test_survivors_cars_debris_and_water_receive_stable_class_ids() -> None:
    # Given the model names in the disaster block
    # When each one is classified
    # Then a flooded survivor stays a person and a flooded car stays a car
    assert label_for_model("survivor_lying_flood_edge") == 1
    assert label_for_model("car_in_flood") == 2
    assert label_for_model("cross_east_debris") == 3
    assert label_for_model("burial_mound") == 3
    assert label_for_model("avenue_flood") == 4
    assert label_for_model("helipad") is None


def test_label_plugins_are_inserted_once() -> None:
    # Given a world snippet with a survivor, a car in flood, water, and a helipad
    source = """<sdf>
  <world name="disaster_block">
    <model name="survivor_lying_flood_edge">
      <static>true</static>
    </model>
    <model name="car_in_flood">
      <static>true</static>
    </model>
    <model name="avenue_flood">
      <static>true</static>
    </model>
    <model name="helipad">
      <static>true</static>
    </model>
  </world>
</sdf>
"""

    # When labels are applied twice
    once = label_sdf(source)
    twice = label_sdf(once.text)

    # Then each scored model has one plugin and the helipad has none
    assert twice.text == once.text
    assert once.text.count("<label>1</label>") == 1
    assert once.text.count("<label>2</label>") == 1
    assert once.text.count("<label>4</label>") == 1
    assert once.text.count("gz-sim-label-system") == 4


def test_the_disaster_block_world_carries_those_labels() -> None:
    # Given the world SDF checked into the repo
    text = _WORLD.read_text(encoding="utf-8")

    # When its labels are counted
    # Then every survivor is a person and the world plugin is present
    assert text.count("<label>1</label>") == 7
    assert "<label>4</label>" in text
    assert 'filename="gz-sim-label-system" name="gz::sim::systems::Label"/>' in text


def test_segmentation_cameras_share_the_left_camera_pose() -> None:
    # Given the stereo model
    root = ET.parse(_MODEL).getroot()
    left = root.find(".//sensor[@name='left_camera']/pose")
    instance = root.find(".//sensor[@name='left_segmentation_instance']")
    semantic = root.find(".//sensor[@name='left_segmentation_semantic']")

    # When the segmentation sensors are compared with the left eye
    # Then they sit on that pose, one instance and one semantic
    assert left is not None and instance is not None and semantic is not None
    assert left.text is not None
    assert left.text.strip() == _text(instance.find("pose")) == _text(semantic.find("pose"))
    assert instance.get("type") == "segmentation"
    assert semantic.get("type") == "segmentation"
    assert _text(instance.find("./camera/segmentation_type")) == "instance"
    assert _text(semantic.find("./camera/segmentation_type")) == "semantic"


def test_a_16_bit_label_image_round_trips_and_the_nearest_pose_is_chosen(tmp_path: Path) -> None:
    # Given a mono16 row of labels 1 and 300, and two poses
    message = SimpleNamespace(
        encoding="mono16",
        width=2,
        height=1,
        step=0,
        data=bytes((1, 0, 44, 1)),
    )
    target = tmp_path / "labels.png"
    poses = (
        StampedPose(0, 1.0, 0.0, 0.0, (0.0, 0.0, 0.0, 1.0)),
        StampedPose(1_000_000_000, 4.0, 0.0, 8.0, (0.0, 0.0, 0.0, 1.0), frame="gazebo_enu"),
    )

    # When the image is written and the pose nearest 1.0 s is chosen
    label_image_to_png(message, target)
    chosen = nearest_pose(poses, 1_000_000_000, slop_ns=20_000_000)
    (tmp_path / "poses.jsonl").write_text(
        json.dumps(pose_record(poses[1])) + "\n",
        encoding="utf-8",
    )
    loaded = load_pose_jsonl(tmp_path / "poses.jsonl")

    # Then the labels survive and the pose is the later camera
    with Image.open(target) as image:
        pixels = list(image.get_flattened_data())
    assert pixels == [1, 300]
    assert chosen is not None
    assert chosen.x_m == 4.0
    assert chosen.z_m == 8.0
    assert loaded[0].frame == "gazebo_enu"
    assert loaded[0].orientation_xyzw == (0.0, 0.0, 0.0, 1.0)


def test_a_sitl_capture_exports_one_hertz_keyframes(tmp_path: Path) -> None:
    # Given three stereo frames, the middle one only 0.2 s after the first
    capture = _capture(tmp_path / "capture")

    # When the bench is exported at 1 Hz
    bench = export_sitl_bench(capture, tmp_path / "bench", hz=1.0)
    dataset = load_bench(bench)

    # Then the middle frame is dropped and the pose is the Gazebo ENU camera
    assert [frame.frame_id for frame in dataset.frames] == [0, 1]
    assert [frame.t_ns for frame in dataset.frames] == [0, 1_000_000_000]
    assert dataset.frames[1].pose.position.z == 8.0
    assert dataset.frames[1].pose_frame == "gazebo_enu"
    assert dataset.scoring.clock == "sim_time"
    assert dataset.frames[0].has_survivor


def test_the_dump_parser_accepts_segmentation_and_pose_topics() -> None:
    # Given the ROS dump script
    module = _dump_module()

    # When segmentation and pose topics are parsed
    args = module._build_parser().parse_args(
        [
            "--left",
            "/left",
            "--right",
            "/right",
            "--output",
            "out",
            "--seg",
            "/seg",
            "--seg-class",
            "/class",
            "--pose",
            "/pose",
        ]
    )

    # Then those topics are kept
    assert args.seg == "/seg"
    assert args.seg_class == "/class"
    assert args.pose == "/pose"


def _text(node: ET.Element | None) -> str:
    assert node is not None and node.text is not None
    return node.text.strip()


def _capture(root: Path) -> Path:
    images = root / "images"
    images.mkdir(parents=True)
    names = (
        "left_0.png",
        "right_0.png",
        "seg_0.png",
        "class_0.png",
        "left_1.png",
        "right_1.png",
        "seg_1.png",
        "class_1.png",
        "left_2.png",
        "right_2.png",
        "seg_2.png",
        "class_2.png",
    )
    for name in names:
        mode = "L" if name.startswith(("seg", "class")) else "RGB"
        Image.new(mode, (4, 2), 1 if mode == "L" else (0, 0, 0)).save(images / name)
    rows = []
    stamps = (0, 200_000_000, 1_000_000_000)
    for index, t_ns in enumerate(stamps):
        rows.append(
            {
                "frame_id": index,
                "t_ns": t_ns,
                "left": f"images/left_{index}.png",
                "right": f"images/right_{index}.png",
                "seg": f"images/seg_{index}.png",
                "seg_class": f"images/class_{index}.png",
                "pose": {
                    "position_m": {"x": 0.0, "y": 0.0, "z": 8.0 if index else 5.0},
                    "orientation_xyzw": [0, 0, 0, 1],
                    "frame": "gazebo_enu",
                },
            }
        )
    (root / "frames.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    (root / "calibration.json").write_text(
        json.dumps(
            {
                "calibration_id": "gazebo-surmap-stereo-v1",
                "width": 4,
                "height": 2,
                "fx": 2.0,
                "fy": 2.0,
                "cx": 2.0,
                "cy": 1.0,
                "baseline_m": 0.07,
            }
        ),
        encoding="utf-8",
    )
    return root


def _dump_module() -> _DumperModule:
    path = Path("scripts/ros2/dump_sitl_capture.py")
    spec = importlib.util.spec_from_file_location("dump_sitl_capture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_DumperModule, module)


class _DumperModule(Protocol):
    def _build_parser(self) -> argparse.ArgumentParser: ...
