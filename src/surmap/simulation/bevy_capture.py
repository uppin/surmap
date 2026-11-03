"""Recorded Bevy sessions: capture directory plus its EuRoC export."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from surmap.simulation.bevy_wire import BevyPair, GroundTruthBox
from surmap.simulation.calibration import StereoCalibrationSpec
from surmap.simulation.euroc_export import export_euroc_session
from surmap.types import Pose, StereoFramePair, Vec3


@dataclass(frozen=True)
class CapturedFrame:
    pair: StereoFramePair
    pose_enu: Pose


@dataclass(frozen=True)
class BevyCapture:
    calibration: StereoCalibrationSpec
    objects: tuple[GroundTruthBox, ...]
    frames: tuple[CapturedFrame, ...]


class CaptureRecorder:
    def __init__(
        self,
        root: Path,
        calibration: StereoCalibrationSpec,
        objects: tuple[GroundTruthBox, ...] = (),
    ) -> None:
        self._root = Path(root)
        self._calibration = calibration
        self._objects = objects
        self._pairs: list[BevyPair] = []
        self._finished = False

    def record_pair(self, pair: BevyPair) -> None:
        self._pairs.append(pair)

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        root = self._root
        root.mkdir(parents=True, exist_ok=True)
        cal = self._calibration
        (root / "calibration.json").write_text(
            json.dumps(
                {
                    "calibration_id": cal.calibration_id,
                    "width": cal.width,
                    "height": cal.height,
                    "fx": cal.fx,
                    "fy": cal.fy,
                    "cx": cal.cx,
                    "cy": cal.cy,
                    "baseline_m": cal.baseline_m,
                    "rate_hz": cal.rate_hz,
                }
            ),
            encoding="utf-8",
        )
        (root / "ground_truth.json").write_text(
            json.dumps(
                [
                    {
                        "id": obj.id,
                        "kind": obj.kind,
                        "min_enu": [obj.min_enu.x, obj.min_enu.y, obj.min_enu.z],
                        "max_enu": [obj.max_enu.x, obj.max_enu.y, obj.max_enu.z],
                    }
                    for obj in self._objects
                ]
            ),
            encoding="utf-8",
        )
        frames: list[StereoFramePair] = []
        lines: list[str] = []
        for pair in self._pairs:
            left_ref = root / "frames" / "left" / f"{pair.t_ns}.png"
            right_ref = root / "frames" / "right" / f"{pair.t_ns}.png"
            left_ref.parent.mkdir(parents=True, exist_ok=True)
            right_ref.parent.mkdir(parents=True, exist_ok=True)
            Image.frombytes("L", (pair.width, pair.height), pair.left_data).save(left_ref)
            Image.frombytes("L", (pair.width, pair.height), pair.right_data).save(right_ref)
            pose = pair.pose_enu
            lines.append(
                json.dumps(
                    {
                        "frame_id": pair.frame_id,
                        "t_ns": pair.t_ns,
                        "width": pair.width,
                        "height": pair.height,
                        "encoding": pair.encoding,
                        "pose_enu": [
                            pose.position.x,
                            pose.position.y,
                            pose.position.z,
                            *pose.orientation_xyzw,
                        ],
                        "left_ref": str(left_ref.relative_to(root)),
                        "right_ref": str(right_ref.relative_to(root)),
                    }
                )
            )
            frames.append(
                StereoFramePair(
                    frame_id=pair.frame_id,
                    t_ns=pair.t_ns,
                    left_ref=str(left_ref),
                    right_ref=str(right_ref),
                    calibration_id=cal.calibration_id,
                )
            )
        (root / "frames.jsonl").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        if frames:
            export_euroc_session(root / "euroc", frames, cal)


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_obj(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be a JSON object")
    out: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{what} keys must be strings")
        out[key] = item
    return out


def _num(obj: dict[str, object], key: str, *, integer: bool = False) -> float:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value) if not integer else float(int(value))


def _vec(value: object) -> Vec3:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("expected three numbers")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("expected three numbers")
        numbers.append(float(item))
    return Vec3(numbers[0], numbers[1], numbers[2])


def load_bevy_capture(root: Path) -> BevyCapture:
    root = Path(root)
    cal_obj = _as_obj(_load_json(root / "calibration.json"), "calibration")
    calibration_id = cal_obj.get("calibration_id")
    if not isinstance(calibration_id, str):
        raise ValueError("calibration_id must be a string")
    calibration = StereoCalibrationSpec(
        calibration_id=calibration_id,
        width=int(_num(cal_obj, "width", integer=True)),
        height=int(_num(cal_obj, "height", integer=True)),
        fx=_num(cal_obj, "fx"),
        fy=_num(cal_obj, "fy"),
        cx=_num(cal_obj, "cx"),
        cy=_num(cal_obj, "cy"),
        baseline_m=_num(cal_obj, "baseline_m"),
        rate_hz=_num(cal_obj, "rate_hz"),
    )
    raw_objects = _load_json(root / "ground_truth.json")
    if not isinstance(raw_objects, list):
        raise ValueError("ground truth must be a list")
    objects: list[GroundTruthBox] = []
    for raw in raw_objects:
        obj = _as_obj(raw, "ground-truth object")
        obj_id, kind = obj.get("id"), obj.get("kind")
        if not isinstance(obj_id, str) or not isinstance(kind, str):
            raise ValueError("ground-truth id/kind must be strings")
        objects.append(
            GroundTruthBox(
                id=obj_id,
                kind=kind,
                min_enu=_vec(obj.get("min_enu")),
                max_enu=_vec(obj.get("max_enu")),
            )
        )
    frames: list[CapturedFrame] = []
    for line in (root / "frames.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = _as_obj(json.loads(line), "frame")
        pose_raw = obj.get("pose_enu")
        if not isinstance(pose_raw, list) or len(pose_raw) != 7:
            raise ValueError("pose_enu must be seven numbers")
        pose_nums: list[float] = []
        for item in pose_raw:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError("pose_enu must be seven numbers")
            pose_nums.append(float(item))
        pose = Pose(
            Vec3(pose_nums[0], pose_nums[1], pose_nums[2]),
            (pose_nums[3], pose_nums[4], pose_nums[5], pose_nums[6]),
        )
        left_ref, right_ref = obj.get("left_ref"), obj.get("right_ref")
        if not isinstance(left_ref, str) or not isinstance(right_ref, str):
            raise ValueError("frame refs must be strings")
        frame_id = int(_num(obj, "frame_id", integer=True))
        t_ns = int(_num(obj, "t_ns", integer=True))
        pair = StereoFramePair(
            frame_id=frame_id,
            t_ns=t_ns,
            left_ref=str(root / left_ref),
            right_ref=str(root / right_ref),
            calibration_id=calibration_id,
        )
        frames.append(CapturedFrame(pair=pair, pose_enu=pose))
    return BevyCapture(calibration=calibration, objects=tuple(objects), frames=tuple(frames))
