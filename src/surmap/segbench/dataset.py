"""Bench directory: images, ground-truth masks, pose, intrinsics, clock.

Layout::

    bench/
      bench.json          scoring frame, clock, and intrinsics
      classes.json        class id -> name ("1" is person)
      frames.jsonl        one record per frame, pose as translation + quaternion
      images/0000.png
      masks/0000_instance.png
      masks/0000_class.png
      clouds/0000.json    optional camera-frame or map-frame points

`t_ns` is the clock named in `bench.json` (simulation time by default).
The pose frame string must match `scoring.map_frame`.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.segbench.conventions import (
    DEFAULT_SCORING,
    ScoringFrame,
    is_survivor_label,
    require_scoring,
)
from surmap.types import Pose, Vec3

_NS_PER_SECOND = 1_000_000_000


@dataclass(frozen=True)
class BenchIntrinsics:
    """Pinhole of the image the mask is drawn on."""

    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    baseline_m: float
    distortion_model: str = "radial-tangential"
    distortion_coefficients: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class BenchFrame:
    """One scored frame. Paths are absolute after a load."""

    frame_id: int
    t_ns: int
    image_path: Path
    instance_mask_path: Path
    class_mask_path: Path
    cloud_path: Path | None
    pose: Pose
    pose_frame: str
    clock: str
    pixel_space: str
    has_survivor: bool
    has_clutter: bool
    intrinsics: BenchIntrinsics


@dataclass(frozen=True)
class BenchDataset:
    """A directory the offline commands can score without a network."""

    root: Path
    scoring: ScoringFrame
    classes: Mapping[int, str]
    intrinsics: BenchIntrinsics
    frames: tuple[BenchFrame, ...]


@dataclass(frozen=True)
class FrameCloud:
    """Points for one frame. `space` is `camera` or `map`."""

    space: str
    points: tuple[Vec3, ...]


def load_bench(directory: Path) -> BenchDataset:
    """Load a bench directory and reject a pose or clock that disagrees with scoring."""
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"bench directory not found: {root}")
    header = _object(json.loads((root / "bench.json").read_text(encoding="utf-8")), "bench.json")
    scoring = _scoring(header.get("scoring"))
    intrinsics = _intrinsics(_object(header["intrinsics"], "intrinsics"))
    classes = _classes(json.loads((root / "classes.json").read_text(encoding="utf-8")))
    frames: list[BenchFrame] = []
    for line_no, line in enumerate(
        (root / "frames.jsonl").read_text(encoding="utf-8").splitlines(), start=1
    ):
        text = line.strip()
        if not text:
            continue
        row = _object(json.loads(text), f"frames.jsonl line {line_no}")
        frames.append(_frame(root, row, line_no, scoring, intrinsics, classes))
    if not frames:
        raise ValueError("frames.jsonl has no frame rows")
    return BenchDataset(root, scoring, classes, intrinsics, tuple(frames))


def select_keyframes(frames: Sequence[BenchFrame], *, hz: float) -> tuple[BenchFrame, ...]:
    """Keep frames at least `1/hz` seconds apart, earliest first."""
    if hz <= 0:
        raise ValueError("keyframe rate must be positive")
    period_ns = int(round(_NS_PER_SECOND / hz))
    if period_ns <= 0:
        raise ValueError("keyframe rate is too high to resolve in nanoseconds")
    ordered = sorted(frames, key=lambda frame: (frame.t_ns, frame.frame_id))
    kept: list[BenchFrame] = []
    last_ns: int | None = None
    for frame in ordered:
        if last_ns is None or frame.t_ns - last_ns >= period_ns:
            kept.append(frame)
            last_ns = frame.t_ns
    return tuple(kept)


def select_dev_set(
    frames: Sequence[BenchFrame],
    *,
    survivor_count: int = 20,
    negative_count: int = 10,
) -> tuple[BenchFrame, ...]:
    """Survivor frames, then hard negatives (clutter and no person).

    The dev set is 20 frames with a survivor and 10 hard negatives unless
    the caller asks for another size. A short flight raises rather than
    padding with empty frames.
    """
    if survivor_count < 0 or negative_count < 0:
        raise ValueError("dev-set counts must be non-negative")
    ordered = sorted(frames, key=lambda frame: (frame.t_ns, frame.frame_id))
    survivors = [frame for frame in ordered if frame.has_survivor]
    negatives = [frame for frame in ordered if not frame.has_survivor and frame.has_clutter]
    if len(survivors) < survivor_count or len(negatives) < negative_count:
        raise ValueError(
            f"need {survivor_count} survivor frames and {negative_count} hard negatives; "
            f"found {len(survivors)} and {len(negatives)}"
        )
    chosen = survivors[:survivor_count] + negatives[:negative_count]
    return tuple(chosen)


def load_cloud(path: Path) -> FrameCloud:
    """Read `{"space": "camera"|"map", "points": [[x, y, z], ...]}`."""
    payload = _object(json.loads(Path(path).read_text(encoding="utf-8")), str(path))
    space = payload.get("space", payload.get("frame", "camera"))
    if space not in ("camera", "map"):
        raise ValueError(f"{path} space must be camera or map")
    raw_points = payload.get("points", [])
    if not isinstance(raw_points, list):
        raise ValueError(f"{path} points must be a list")
    points: list[Vec3] = []
    for index, item in enumerate(raw_points):
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError(f"{path} point {index} must be [x, y, z]")
        coords = [item[0], item[1], item[2]]
        if any(isinstance(value, bool) or not isinstance(value, int | float) for value in coords):
            raise ValueError(f"{path} point {index} must be numbers")
        points.append(Vec3(float(coords[0]), float(coords[1]), float(coords[2])))
    return FrameCloud(str(space), tuple(points))


def read_label_image(path: Path) -> NDArray[np.int32]:
    """Instance or class ids. RGB images use the first channel."""
    with Image.open(path) as image:
        array = cast("NDArray[np.generic]", np.asarray(image))
    if array.ndim == 3:
        array = array[:, :, 0]
    if array.ndim != 2:
        raise ValueError(f"{path} is not a two-dimensional label image")
    return array.astype(np.int32)


def write_label_image(path: Path, labels: NDArray[np.int32]) -> None:
    """Write class or instance ids as a PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    highest = 0 if labels.size == 0 else int(np.max(labels))
    if highest < 0:
        raise ValueError("label images cannot store negative ids")
    if highest <= 255:
        Image.fromarray(labels.astype(np.uint8), mode="L").save(path)
        return
    if highest > 65535:
        raise ValueError("label images only store ids up to 65535")
    Image.fromarray(labels.astype(np.uint16), mode="I;16").save(path)


def export_sitl_bench(
    capture: Path,
    destination: Path,
    *,
    hz: float = 1.0,
    scoring: ScoringFrame | None = None,
) -> Path:
    """Turn one SITL capture with segmentation and pose into a bench at `hz` keyframes."""
    chosen = require_scoring(scoring if scoring is not None else DEFAULT_SCORING)
    root = Path(capture)
    header = _object(
        json.loads((root / "calibration.json").read_text(encoding="utf-8")),
        "calibration.json",
    )
    intrinsics = BenchIntrinsics(
        width=_int_field(header, "width"),
        height=_int_field(header, "height"),
        fx=_float_field(header, "fx"),
        fy=_float_field(header, "fy"),
        cx=_float_field(header, "cx"),
        cy=_float_field(header, "cy"),
        baseline_m=_float_field(header, "baseline_m"),
    )
    rows = _jsonl_objects(root / "frames.jsonl")
    if not rows:
        raise ValueError("frames.jsonl has no frame rows")
    poses = _load_pose_sidecar(root / "poses.jsonl")
    staged: list[tuple[int, dict[str, object]]] = []
    for index, row in enumerate(rows):
        pose_payload = _row_pose(row, poses)
        if pose_payload is None:
            continue
        if "seg" not in row and "instance_mask" not in row:
            continue
        staged.append((index, {**row, "pose": pose_payload}))
    if not staged:
        raise ValueError(
            "no capture frame has both a segmentation image and a pose; dump with --seg and --pose"
        )
    period_ns = int(round(_NS_PER_SECOND / hz))
    if hz <= 0 or period_ns <= 0:
        raise ValueError("keyframe rate must be positive")
    staged.sort(key=lambda item: _int_value(item[1].get("t_ns"), "t_ns"))
    kept: list[tuple[int, dict[str, object]]] = []
    last_ns: int | None = None
    for item in staged:
        t_ns = _int_value(item[1].get("t_ns"), "t_ns")
        if last_ns is None or t_ns - last_ns >= period_ns:
            kept.append(item)
            last_ns = t_ns
    destination.mkdir(parents=True, exist_ok=True)
    classes = {1: "person", 2: "car", 3: "debris", 4: "water"}
    (destination / "classes.json").write_text(
        json.dumps({str(key): value for key, value in classes.items()}, indent=2) + "\n",
        encoding="utf-8",
    )
    bench_header = {
        "scoring": {
            "map_frame": chosen.map_frame,
            "pixel_space": chosen.pixel_space,
            "clock": chosen.clock,
            "match_radius_m": chosen.match_radius_m,
        },
        "intrinsics": {
            "width": intrinsics.width,
            "height": intrinsics.height,
            "fx": intrinsics.fx,
            "fy": intrinsics.fy,
            "cx": intrinsics.cx,
            "cy": intrinsics.cy,
            "baseline_m": intrinsics.baseline_m,
            "distortion_model": intrinsics.distortion_model,
            "distortion_coefficients": list(intrinsics.distortion_coefficients),
        },
        "mask_note": (
            "instance from --seg, class from --seg-class. "
            "A missing class image is copied from the instance image."
        ),
    }
    (destination / "bench.json").write_text(
        json.dumps(bench_header, indent=2) + "\n", encoding="utf-8"
    )
    lines: list[str] = []
    for frame_id, (_, row) in enumerate(kept):
        left = _rel_file(root, row, "left", "left_ref")
        instance_rel = _rel_file(root, row, "seg", "instance_mask")
        class_key = "seg_class" if "seg_class" in row else "class_mask"
        if class_key in row:
            class_rel = _rel_file(root, row, class_key, class_key)
        else:
            class_rel = instance_rel
        image_name = f"images/{frame_id:04d}.png"
        instance_name = f"masks/{frame_id:04d}_instance.png"
        class_name = f"masks/{frame_id:04d}_class.png"
        _copy(root / left, destination / image_name)
        _copy(root / instance_rel, destination / instance_name)
        _copy(root / class_rel, destination / class_name)
        cloud_name: str | None = None
        cloud_key = row.get("cloud")
        if isinstance(cloud_key, str) and cloud_key:
            cloud_name = f"clouds/{frame_id:04d}.json"
            _copy(root / cloud_key, destination / cloud_name)
        pose_body = row["pose"]
        if not isinstance(pose_body, dict):
            raise ValueError("pose must be an object")
        record: dict[str, object] = {
            "frame_id": frame_id,
            "t_ns": _int_value(row.get("t_ns"), "t_ns"),
            "clock": chosen.clock,
            "pixel_space": chosen.pixel_space,
            "left_ref": image_name,
            "instance_mask": instance_name,
            "class_mask": class_name,
            "pose": pose_body,
        }
        if cloud_name is not None:
            record["cloud"] = cloud_name
        lines.append(json.dumps(record))
    (destination / "frames.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def _frame(
    root: Path,
    row: dict[str, object],
    line_no: int,
    scoring: ScoringFrame,
    intrinsics: BenchIntrinsics,
    classes: Mapping[int, str],
) -> BenchFrame:
    where = f"frames.jsonl line {line_no}"
    frame_id = _int_value(row.get("frame_id"), f"{where} frame_id")
    t_ns = _int_value(row.get("t_ns"), f"{where} t_ns")
    clock = _text_or(row.get("clock"), scoring.clock, f"{where} clock")
    pixel_space = _text_or(row.get("pixel_space"), scoring.pixel_space, f"{where} pixel_space")
    if clock != scoring.clock:
        raise ValueError(f"{where} clock is {clock}, scoring clock is {scoring.clock}")
    if pixel_space != scoring.pixel_space:
        raise ValueError(
            f"{where} pixel_space is {pixel_space}, scoring pixel_space is {scoring.pixel_space}"
        )
    pose_body = _object(row.get("pose"), f"{where} pose")
    pose_frame = _text_or(pose_body.get("frame"), scoring.map_frame, f"{where} pose.frame")
    if pose_frame != scoring.map_frame:
        raise ValueError(
            f"{where} pose frame is {pose_frame}, scoring map_frame is {scoring.map_frame}"
        )
    image_path = _existing(root, row, "left_ref", where)
    instance_path = _existing(root, row, "instance_mask", where)
    class_path = _existing(root, row, "class_mask", where)
    cloud_raw = row.get("cloud")
    cloud_path = _existing(root, row, "cloud", where) if isinstance(cloud_raw, str) else None
    instance = read_label_image(instance_path)
    class_image = read_label_image(class_path)
    if instance.shape != class_image.shape:
        raise ValueError(f"{where} instance and class masks differ in shape")
    if instance.shape != (intrinsics.height, intrinsics.width):
        raise ValueError(f"{where} mask shape does not match intrinsics")
    has_survivor = False
    has_clutter = False
    for class_id in (int(value) for value in np.unique(class_image)):
        if class_id == 0:
            continue
        if is_survivor_label(classes.get(class_id, "")):
            has_survivor = True
        else:
            has_clutter = True
    return BenchFrame(
        frame_id=frame_id,
        t_ns=t_ns,
        image_path=image_path,
        instance_mask_path=instance_path,
        class_mask_path=class_path,
        cloud_path=cloud_path,
        pose=_pose(pose_body, where),
        pose_frame=pose_frame,
        clock=clock,
        pixel_space=pixel_space,
        has_survivor=has_survivor,
        has_clutter=has_clutter,
        intrinsics=intrinsics,
    )


def _pose(body: dict[str, object], where: str) -> Pose:
    position = _object(body.get("position_m"), f"{where} position_m")
    raw_quat = body.get("orientation_xyzw")
    if not isinstance(raw_quat, list) or len(raw_quat) != 4:
        raise ValueError(f"{where} orientation_xyzw must be [x, y, z, w]")
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in raw_quat):
        raise ValueError(f"{where} orientation_xyzw must be numbers")
    return Pose(
        Vec3(
            _float_value(position.get("x"), f"{where} position x"),
            _float_value(position.get("y"), f"{where} position y"),
            _float_value(position.get("z"), f"{where} position z"),
        ),
        (
            float(raw_quat[0]),
            float(raw_quat[1]),
            float(raw_quat[2]),
            float(raw_quat[3]),
        ),
    )


def _scoring(raw: object) -> ScoringFrame:
    if raw is None:
        return DEFAULT_SCORING
    body = _object(raw, "scoring")
    allowed = {"map_frame", "pixel_space", "clock", "match_radius_m"}
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise ValueError(f"scoring has unknown fields: {', '.join(unknown)}")
    frame = ScoringFrame(
        map_frame=_text_or(body.get("map_frame"), DEFAULT_SCORING.map_frame, "map_frame"),
        pixel_space=_text_or(body.get("pixel_space"), DEFAULT_SCORING.pixel_space, "pixel_space"),
        clock=_text_or(body.get("clock"), DEFAULT_SCORING.clock, "clock"),
        match_radius_m=(
            DEFAULT_SCORING.match_radius_m
            if "match_radius_m" not in body
            else _float_value(body.get("match_radius_m"), "match_radius_m")
        ),
    )
    return require_scoring(frame)


def _intrinsics(body: dict[str, object]) -> BenchIntrinsics:
    coefficients = body.get("distortion_coefficients", [0.0, 0.0, 0.0, 0.0])
    if not isinstance(coefficients, list) or len(coefficients) != 4:
        raise ValueError("distortion_coefficients must be [k1, k2, p1, p2]")
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in coefficients):
        raise ValueError("distortion_coefficients must be numbers")
    return BenchIntrinsics(
        width=_int_field(body, "width"),
        height=_int_field(body, "height"),
        fx=_float_field(body, "fx"),
        fy=_float_field(body, "fy"),
        cx=_float_field(body, "cx"),
        cy=_float_field(body, "cy"),
        baseline_m=_float_field(body, "baseline_m"),
        distortion_model=_text_or(
            body.get("distortion_model"), "radial-tangential", "distortion_model"
        ),
        distortion_coefficients=(
            float(coefficients[0]),
            float(coefficients[1]),
            float(coefficients[2]),
            float(coefficients[3]),
        ),
    )


def _classes(raw: object) -> dict[int, str]:
    body = _object(raw, "classes.json")
    classes: dict[int, str] = {}
    for key, value in body.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"class {key} must be a name")
        try:
            class_id = int(key)
        except ValueError as exc:
            raise ValueError(f"class id {key} is not an integer") from exc
        classes[class_id] = value.strip()
    return classes


def _existing(root: Path, row: dict[str, object], key: str, where: str) -> Path:
    raw = row.get(key)
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{where} is missing {key}")
    path = (root / raw).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{where} {key} not found: {raw}")
    return path


def _row_pose(
    row: dict[str, object],
    poses: Sequence[tuple[int, dict[str, object]]],
) -> dict[str, object] | None:
    raw = row.get("pose")
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    if not poses:
        return None
    t_ns = _int_value(row.get("t_ns"), "t_ns")
    nearest = min(poses, key=lambda item: abs(item[0] - t_ns))
    slop = 50_000_000
    if abs(nearest[0] - t_ns) > slop:
        return None
    return nearest[1]


def _load_pose_sidecar(path: Path) -> tuple[tuple[int, dict[str, object]], ...]:
    if not path.is_file():
        return ()
    found: list[tuple[int, dict[str, object]]] = []
    for row in _jsonl_objects(path):
        t_ns = _int_value(row.get("t_ns"), "poses.jsonl t_ns")
        found.append((t_ns, row))
    return tuple(found)


def _jsonl_objects(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        rows.append(_object(json.loads(text), f"{path.name} line {line_no}"))
    return rows


def _rel_file(root: Path, row: dict[str, object], *keys: str) -> str:
    for key in keys:
        raw = row.get(key)
        if isinstance(raw, str) and raw:
            if not (root / raw).is_file():
                raise FileNotFoundError(f"{key} not found: {raw}")
            return raw
    raise ValueError(f"missing one of {', '.join(keys)}")


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _object(raw: object, where: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object")
    return {str(key): value for key, value in raw.items()}


def _text_or(raw: object, default: str, where: str) -> str:
    if raw is None:
        return default
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{where} must be text")
    return raw.strip()


def _float_field(body: dict[str, object], key: str) -> float:
    if key not in body:
        raise ValueError(f"missing {key}")
    return _float_value(body[key], key)


def _int_field(body: dict[str, object], key: str) -> int:
    if key not in body:
        raise ValueError(f"missing {key}")
    return _int_value(body[key], key)


def _float_value(raw: object, where: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ValueError(f"{where} must be a number")
    return float(raw)


def _int_value(raw: object, where: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{where} must be an integer")
    return raw
