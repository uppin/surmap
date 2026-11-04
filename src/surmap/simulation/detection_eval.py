"""Scoring on-board detections against a simulation capture's ground truth.

Each ground-truth box whose kind a COCO detector can name (`car`, `person`) — and each vehicle
(`car`, `bus`, `truck`, `train`) that only `object_tracks.jsonl` places, given its class's
footprint and recorded heading — is projected onto the
left image of every frame (`bevy_ground_truth.project_box`). It is *expected* in that frame when
most of its projected box lies inside the image and the box is big enough to resolve. A
detection *finds* an expected object when its label is one the kind answers to and its box
overlaps the expected box; every other detection is a false positive. Occlusion is not tested
(captures carry no depth), so an object behind a building still counts as expected.

`building`, `collapsed_building`, `debris`, `box` and `fire` are not COCO classes: no on-board
detector can name them, so they are never expected (SAM labels them, docs/meta-sam.md).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.simulation.bevy_capture import BevyCapture, CapturedFrame
from surmap.simulation.bevy_ground_truth import project_box
from surmap.simulation.bevy_wire import GroundTruthBox
from surmap.simulation.calibration import StereoCalibrationSpec
from surmap.types import Detection, Pose, Vec3

Box = tuple[float, float, float, float]

# The COCO labels each ground-truth kind answers to.
COCO_LABELS: Mapping[str, frozenset[str]] = {
    "car": frozenset({"car", "truck", "bus"}),
    "bus": frozenset({"bus"}),
    "truck": frozenset({"truck"}),
    "train": frozenset({"train"}),
    "person": frozenset({"person"}),
}
# The kinds that are vehicles: a detection with one of these labels on a missed vehicle is a
# confusion (`as_another_vehicle`), not a false positive.
VEHICLE_KINDS = ("car", "bus", "truck", "train")
VEHICLE_LABELS = frozenset({"car", "bus", "truck", "train"})
# (length, width, height) in metres of each vehicle class, as `assets/vehicle/<class>.vehicle.json`
# of the renderer declares them. A train is its locomotive; carriages are not tracked.
VEHICLE_FOOTPRINT_M: Mapping[str, tuple[float, float, float]] = {
    "car": (4.2, 1.8, 1.2),
    "bus": (11.0, 3.5, 3.4),
    "truck": (6.6, 3.4, 3.6),
    "train": (8.1, 2.9, 6.1),
}
# An expected box is at least this many pixels on its shorter side, inside the image.
MIN_SIDE_PX = 12.0
# At least this fraction of the projected box lies inside the image.
MIN_INSIDE = 0.5
# A detection finds an expected object at this intersection-over-union or more.
MIN_IOU = 0.3


class FrameDetector(Protocol):
    """What `CoralDetector` offers: detections on one RGB frame."""

    def detect(self, rgb: NDArray[np.uint8], frame_id: int) -> tuple[Detection, ...]: ...


@dataclass(frozen=True)
class ExpectedObject:
    id: str
    kind: str
    box_xyxy: Box


@dataclass(frozen=True)
class FrameScore:
    hit_ids: frozenset[str]
    false_positives: tuple[Detection, ...]
    as_another_vehicle: frozenset[str] = frozenset()


@dataclass
class KindScore:
    """Object-frames: one per (object, frame) the object is expected in."""

    visible: int = 0
    found: int = 0
    # Vehicles not found, but covered by a detection with another vehicle's label.
    as_another_vehicle: int = 0

    @property
    def hit_rate(self) -> float:
        return self.found / self.visible if self.visible else 0.0


@dataclass
class DetectionReport:
    kinds: dict[str, KindScore] = field(default_factory=dict)
    # Per object id: (frames expected, frames found).
    objects: dict[str, tuple[int, int]] = field(default_factory=dict)
    false_positives: dict[str, int] = field(default_factory=dict)
    # Person object-frames by the pose the person holds, where the capture's tracks carry it.
    poses: dict[str, KindScore] = field(default_factory=dict)
    frames: int = 0


def _area(box: Box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _iou(a: Box, b: Box) -> float:
    inter = _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def _moved(box: GroundTruthBox, to: Vec3) -> GroundTruthBox:
    dx = to.x - (box.min_enu.x + box.max_enu.x) / 2.0
    dy = to.y - (box.min_enu.y + box.max_enu.y) / 2.0
    return GroundTruthBox(
        id=box.id,
        kind=box.kind,
        min_enu=Vec3(box.min_enu.x + dx, box.min_enu.y + dy, box.min_enu.z),
        max_enu=Vec3(box.max_enu.x + dx, box.max_enu.y + dy, box.max_enu.z),
    )


def _vehicle_box(obj_id: str, kind: str, at: Vec3, heading_deg: float) -> GroundTruthBox:
    """The axis-aligned box around a vehicle's yawed footprint, its base at `at`."""
    length, width, height = VEHICLE_FOOTPRINT_M[kind]
    cos, sin = abs(math.cos(math.radians(heading_deg))), abs(math.sin(math.radians(heading_deg)))
    half_x, half_y = (length * cos + width * sin) / 2.0, (length * sin + width * cos) / 2.0
    return GroundTruthBox(
        id=obj_id,
        kind=kind,
        min_enu=Vec3(at.x - half_x, at.y - half_y, at.z),
        max_enu=Vec3(at.x + half_x, at.y + half_y, at.z + height),
    )


def _with_tracked_vehicles(
    objects: Sequence[GroundTruthBox],
    tracks: Mapping[str, Vec3] | None,
    kinds: Mapping[str, str] | None,
    yaw_deg: Mapping[str, float] | None,
) -> list[GroundTruthBox]:
    """`objects` plus a box for every tracked vehicle the ground truth does not list."""
    boxes = list(objects)
    listed = {obj.id for obj in objects}
    for obj_id, at in (tracks or {}).items():
        kind = (kinds or {}).get(obj_id)
        if obj_id not in listed and kind is not None and kind in VEHICLE_FOOTPRINT_M:
            boxes.append(_vehicle_box(obj_id, kind, at, (yaw_deg or {}).get(obj_id, 0.0)))
    return boxes


def visible_objects(
    objects: Sequence[GroundTruthBox],
    rig: Pose,
    calibration: StereoCalibrationSpec,
    *,
    tracks: Mapping[str, Vec3] | None = None,
    kinds: Mapping[str, str] | None = None,
    yaw_deg: Mapping[str, float] | None = None,
    min_side_px: float = MIN_SIDE_PX,
    min_inside: float = MIN_INSIDE,
) -> tuple[ExpectedObject, ...]:
    """The objects a COCO detector should find in the frame seen from `rig`.

    A tracked object (a walking person) is moved to its frame position first; a tracked
    vehicle the ground truth does not list (`kinds`, `yaw_deg` by id) is placed there. With the
    thresholds at zero it lists every object present in the image, resolvable or not.
    """
    expected: list[ExpectedObject] = []
    for obj in _with_tracked_vehicles(objects, tracks, kinds, yaw_deg):
        if obj.kind not in COCO_LABELS:
            continue
        placed = _moved(obj, tracks[obj.id]) if tracks and obj.id in tracks else obj
        polygon = project_box(placed, rig, calibration)
        if not polygon:
            continue
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        full: Box = (min(xs), min(ys), max(xs), max(ys))
        inside: Box = (
            max(full[0], 0.0),
            max(full[1], 0.0),
            min(full[2], float(calibration.width)),
            min(full[3], float(calibration.height)),
        )
        if _area(full) <= 0 or _area(inside) <= 0 or _area(inside) / _area(full) < min_inside:
            continue
        if min(inside[2] - inside[0], inside[3] - inside[1]) < min_side_px:
            continue
        expected.append(ExpectedObject(obj.id, obj.kind, inside))
    return tuple(expected)


def _best(
    detection: Detection, objects: Sequence[ExpectedObject], taken: set[str]
) -> ExpectedObject | None:
    candidates = [
        (_iou(detection.box_xyxy, obj.box_xyxy), obj)
        for obj in objects
        if obj.id not in taken and detection.label in COCO_LABELS[obj.kind]
    ]
    best = max(candidates, key=lambda c: c[0], default=None)
    return best[1] if best is not None and best[0] >= MIN_IOU else None


def _covered_vehicle(
    detection: Detection, objects: Sequence[ExpectedObject], hits: set[str]
) -> ExpectedObject | None:
    """The missed vehicle a vehicle-labelled detection sits on (called something else)."""
    if detection.label not in VEHICLE_LABELS:
        return None
    candidates = [
        (_iou(detection.box_xyxy, obj.box_xyxy), obj)
        for obj in objects
        if obj.kind in VEHICLE_KINDS and obj.id not in hits
    ]
    best = max(candidates, key=lambda c: c[0], default=None)
    return best[1] if best is not None and best[0] >= MIN_IOU else None


def score_frame(
    expected: Sequence[ExpectedObject],
    detections: Sequence[Detection],
    *,
    unresolved: Sequence[ExpectedObject] = (),
) -> FrameScore:
    """Match detections, best score first, to the expected object they overlap most.

    A detection of an object present but too small or too clipped to be expected
    (`unresolved`) is neither a hit nor a false positive.
    """
    hits: set[str] = set()
    unmatched: list[Detection] = []
    for detection in sorted(detections, key=lambda d: -d.score):
        found = _best(detection, expected, hits)
        if found is not None:
            hits.add(found.id)
        else:
            unmatched.append(detection)
    confused: set[str] = set()
    false_positives: list[Detection] = []
    for detection in unmatched:
        vehicle = _covered_vehicle(detection, expected, hits)
        if vehicle is not None:
            confused.add(vehicle.id)
        elif _best(detection, unresolved, set()) is None:
            false_positives.append(detection)
    return FrameScore(frozenset(hits), tuple(false_positives), frozenset(confused))


def _seen_in(
    capture: BevyCapture, frame: CapturedFrame, *, min_side_px: float, min_inside: float
) -> tuple[ExpectedObject, ...]:
    return visible_objects(
        capture.objects,
        frame.pose_enu,
        capture.calibration,
        tracks=capture.object_tracks.get(frame.pair.t_ns),
        kinds=capture.object_kinds,
        yaw_deg=capture.object_yaw_deg.get(frame.pair.t_ns),
        min_side_px=min_side_px,
        min_inside=min_inside,
    )


def score_capture(
    capture: BevyCapture, detections: Mapping[int, Sequence[Detection]]
) -> DetectionReport:
    """Every frame's expected objects against its detections (keyed by `frame_id`)."""
    report = DetectionReport(kinds={kind: KindScore() for kind in COCO_LABELS})
    seen: Counter[str] = Counter()
    found: Counter[str] = Counter()
    false_positives: Counter[str] = Counter()
    for frame in capture.frames:
        expected = _seen_in(capture, frame, min_side_px=MIN_SIDE_PX, min_inside=MIN_INSIDE)
        expected_ids = {obj.id for obj in expected}
        present = _seen_in(capture, frame, min_side_px=0.0, min_inside=0.0)
        unresolved = tuple(obj for obj in present if obj.id not in expected_ids)
        score = score_frame(
            expected, detections.get(frame.pair.frame_id, ()), unresolved=unresolved
        )
        poses = capture.object_poses.get(frame.pair.t_ns, {})
        for obj in expected:
            seen[obj.id] += 1
            report.kinds[obj.kind].visible += 1
            by_pose = (
                report.poses.setdefault(poses[obj.id], KindScore()) if obj.id in poses else None
            )
            if by_pose is not None:
                by_pose.visible += 1
            if obj.id in score.hit_ids:
                found[obj.id] += 1
                report.kinds[obj.kind].found += 1
            elif obj.id in score.as_another_vehicle:
                report.kinds[obj.kind].as_another_vehicle += 1
            if obj.id in score.hit_ids and by_pose is not None:
                by_pose.found += 1
        false_positives.update(d.label for d in score.false_positives)
        report.frames += 1
    report.objects = {obj_id: (seen[obj_id], found[obj_id]) for obj_id in sorted(seen)}
    report.false_positives = dict(false_positives)
    return report


def detect_capture(
    capture: BevyCapture, detector: FrameDetector
) -> dict[int, tuple[Detection, ...]]:
    """Every frame's detections (by `frame_id`), on its colour left image when the capture has
    one, else on its grey left eye (repeated into three channels, as the detector takes RGB)."""
    detections: dict[int, tuple[Detection, ...]] = {}
    for frame in capture.frames:
        path = Path(frame.left_rgb_ref or frame.pair.left_ref)
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        detections[frame.pair.frame_id] = detector.detect(rgb, frame.pair.frame_id)
    return detections
