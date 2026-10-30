"""Multi-frame label fusion on a voxel log-odds grid.

Evidence is written only for voxels that survive the z-buffer. A masked
voxel receives `w * logit(clip(sam_score * label_conf, 0.05, 0.95))`.
`w` is visibility, times distance decay, times an edge down-weight.
A visible unmasked voxel receives negative evidence. Voxels above the
occupancy threshold are clustered into landmarks.

Muse is not called here. `label_requests` yields one crop per landmark,
the best view, so a labeller runs once per landmark rather than once
per detection.
"""

from __future__ import annotations

import io
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.labelling.baseten_muse import LabelClient, ObjectLabel
from surmap.segbench.conventions import DEFAULT_SCORING, ScoringFrame
from surmap.segbench.masks import BoolMask, mask_boundary, rasterize_polygon
from surmap.segbench.project import VisiblePoint, visible_points
from surmap.survey.stereo import StereoRig
from surmap.types import Pose, Vec3

CROP_PADDING_PX = 16


@dataclass(frozen=True)
class FusionConfig:
    """Voxel size and the weights on one observation."""

    voxel_m: float = 0.2
    probability_low: float = 0.05
    probability_high: float = 0.95
    occupancy_log_odds: float = 0.0
    cluster_eps_m: float = 0.6
    cluster_min_points: int = 1
    distance_decay_m: float = 20.0
    edge_band_px: float = 3.0
    edge_floor: float = 0.25
    negative_gain: float = 1.0


@dataclass(frozen=True)
class MaskEvidence:
    """One SAM polygon and the confidence that multiplies its score."""

    mask_id: str
    polygon: tuple[tuple[float, float], ...]
    score: float
    label: str
    label_confidence: float = 1.0
    box_xyxy: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    track_id: int | None = None
    score_missing: bool = False


@dataclass(frozen=True)
class FusionFrame:
    """Points and masks already expressed in the scoring map frame's pose."""

    frame_id: int
    t_ns: int
    pose: Pose
    rig: StereoRig
    width: int
    height: int
    points: tuple[Vec3, ...]
    detections: tuple[MaskEvidence, ...]
    points_are_map: bool = False
    source: str = ""
    model_id: str = ""


@dataclass(frozen=True)
class BenchLandmark:
    """A fused object, shaped like the architecture `Landmark`."""

    landmark_id: str
    centroid: Vec3
    map_frame: str
    frame_ids: tuple[int, ...]
    mask_ids: tuple[str, ...]
    track_ids: tuple[int, ...]
    label: str
    description: str
    confidence: float
    provider: str
    model_id: str
    prompt_version: str
    first_seen_ns: int
    last_seen_ns: int
    observation_count: int
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    altitude_m: float | None = None
    best_frame_id: int = 0
    best_box_xyxy: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    sam_source: str = ""
    sam_model_id: str = ""


@dataclass(frozen=True)
class LabelRequest:
    """One Muse call: the landmark's best crop, not every detection."""

    landmark_id: str
    frame_id: int
    box_xyxy: tuple[float, float, float, float]
    coarse_label: str
    xyz: Vec3
    padding_px: int = CROP_PADDING_PX


def logit(probability: float) -> float:
    """Log-odds of a probability clipped away from 0 and 1."""
    clipped = min(1.0 - 1e-6, max(1e-6, probability))
    return math.log(clipped / (1.0 - clipped))


def clipped_probability(sam_score: float, label_confidence: float, config: FusionConfig) -> float:
    """`clip(sam_score * label_conf, low, high)`."""
    product = sam_score * label_confidence
    return min(config.probability_high, max(config.probability_low, product))


def evidence_weight(depth_m: float, edge_distance: float, config: FusionConfig) -> float:
    """Visibility (1 for a z-buffer winner) times distance decay times edge weight."""
    if config.distance_decay_m <= 0:
        raise ValueError("distance_decay_m must be positive")
    decay = math.exp(-max(depth_m, 0.0) / config.distance_decay_m)
    if config.edge_band_px <= 0:
        edge = 1.0
    else:
        fraction = min(1.0, max(0.0, edge_distance) / config.edge_band_px)
        edge = config.edge_floor + (1.0 - config.edge_floor) * fraction
    return decay * edge


def fuse(
    frames: Sequence[FusionFrame],
    *,
    config: FusionConfig | None = None,
    scoring: ScoringFrame | None = None,
) -> tuple[BenchLandmark, ...]:
    """Fuse posed frames into landmarks. Muse is not called."""
    chosen = config if config is not None else FusionConfig()
    frame_name = (scoring if scoring is not None else DEFAULT_SCORING).map_frame
    if chosen.voxel_m <= 0:
        raise ValueError("voxel_m must be positive")
    voxels: dict[tuple[int, int, int], _Voxel] = {}
    for frame in frames:
        _integrate(frame, voxels, chosen)
    occupied = [
        voxel
        for voxel in voxels.values()
        if voxel.log_odds > chosen.occupancy_log_odds and voxel.count > 0
    ]
    if not occupied:
        return ()
    groups = _cluster(occupied, chosen.cluster_eps_m, chosen.cluster_min_points)
    landmarks: list[BenchLandmark] = []
    for group in groups:
        landmark = _landmark(group, frame_name, len(landmarks) + 1)
        if landmark is not None:
            landmarks.append(landmark)
    landmarks.sort(
        key=lambda item: (item.centroid.x, item.centroid.y, item.centroid.z, item.landmark_id)
    )
    renumbered = [
        replace(item, landmark_id=f"lm-{index}") for index, item in enumerate(landmarks, start=1)
    ]
    return tuple(renumbered)


def label_requests(
    landmarks: Sequence[BenchLandmark],
    *,
    padding_px: int = CROP_PADDING_PX,
) -> tuple[LabelRequest, ...]:
    """One request per landmark, aimed at its highest-weight crop."""
    if padding_px < 0:
        raise ValueError("padding_px must be non-negative")
    return tuple(
        LabelRequest(
            landmark_id=landmark.landmark_id,
            frame_id=landmark.best_frame_id,
            box_xyxy=landmark.best_box_xyxy,
            coarse_label=landmark.label,
            xyz=landmark.centroid,
            padding_px=padding_px,
        )
        for landmark in landmarks
    )


def label_landmarks(
    landmarks: Sequence[BenchLandmark],
    images: Mapping[int, bytes],
    labeller: LabelClient,
    *,
    provider: str,
    padding_px: int = CROP_PADDING_PX,
) -> tuple[BenchLandmark, ...]:
    """Call `labeller` once per landmark and write the reply onto that landmark."""
    labelled: list[BenchLandmark] = []
    for landmark, request in zip(
        landmarks, label_requests(landmarks, padding_px=padding_px), strict=True
    ):
        image = images.get(request.frame_id)
        if image is None:
            raise ValueError(f"no image for frame {request.frame_id}")
        crop = crop_jpeg(image, request.box_xyxy, padding_px=request.padding_px)
        result = labeller.label(crop, request.coarse_label, request.xyz)
        labelled.append(_with_label(landmark, result, provider))
    return tuple(labelled)


def crop_jpeg(
    image: bytes,
    box_xyxy: tuple[float, float, float, float],
    *,
    padding_px: int,
) -> bytes:
    """JPEG of the box expanded by `padding_px` and clamped to the image."""
    with Image.open(io.BytesIO(image)) as opened:
        rgb = opened.convert("RGB")
    width, height = rgb.size
    x0, y0, x1, y1 = box_xyxy
    left = max(0, math.floor(x0) - padding_px)
    top = max(0, math.floor(y0) - padding_px)
    right = min(width, math.ceil(x1) + padding_px)
    bottom = min(height, math.ceil(y1) + padding_px)
    if right <= left or bottom <= top:
        raise ValueError("detection crop is empty")
    crop = rgb.crop((left, top, right, bottom))
    buffer = io.BytesIO()
    crop.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


class _Voxel:
    def __init__(self) -> None:
        self.log_odds = 0.0
        self.sum_x = 0.0
        self.sum_y = 0.0
        self.sum_z = 0.0
        self.count = 0
        self.frames: set[int] = set()
        self.masks: set[str] = set()
        self.tracks: set[int] = set()
        self.labels: dict[str, float] = {}
        self.first_ns = 0
        self.last_ns = 0
        self.best_weight = -1.0
        self.best_frame_id = 0
        self.best_box = (0.0, 0.0, 0.0, 0.0)
        self.source = ""
        self.model_id = ""

    @property
    def centroid(self) -> Vec3:
        scale = float(self.count)
        return Vec3(self.sum_x / scale, self.sum_y / scale, self.sum_z / scale)


def _integrate(
    frame: FusionFrame,
    voxels: dict[tuple[int, int, int], _Voxel],
    config: FusionConfig,
) -> None:
    winners = visible_points(
        frame.points,
        frame.rig,
        frame.width,
        frame.height,
        frame.pose,
        points_are_map=frame.points_are_map,
    )
    claimed: set[tuple[int, int]] = set()
    for detection in frame.detections:
        mask = rasterize_polygon(detection.polygon, frame.width, frame.height)
        distance = edge_distance_px(mask)
        probability = (
            config.probability_low
            if detection.score_missing
            else clipped_probability(detection.score, detection.label_confidence, config)
        )
        update = logit(probability)
        for point in winners:
            row = int(point.v)
            column = int(point.u)
            if not mask[row, column]:
                continue
            claimed.add((column, row))
            weight = evidence_weight(point.depth_m, float(distance[row, column]), config)
            _add_positive(
                voxels, point, weight * update, weight * detection.score, detection, frame, config
            )
    for point in winners:
        pixel = (int(point.u), int(point.v))
        if pixel in claimed:
            continue
        weight = evidence_weight(point.depth_m, config.edge_band_px, config)
        key = _voxel_key(point.mapped, config.voxel_m)
        voxel = voxels.setdefault(key, _Voxel())
        voxel.log_odds -= config.negative_gain * weight


def _add_positive(
    voxels: dict[tuple[int, int, int], _Voxel],
    point: VisiblePoint,
    log_update: float,
    rank: float,
    detection: MaskEvidence,
    frame: FusionFrame,
    config: FusionConfig,
) -> None:
    voxel = voxels.setdefault(_voxel_key(point.mapped, config.voxel_m), _Voxel())
    voxel.log_odds += log_update
    voxel.sum_x += point.mapped.x
    voxel.sum_y += point.mapped.y
    voxel.sum_z += point.mapped.z
    voxel.count += 1
    if frame.frame_id not in voxel.frames and voxel.frames:
        voxel.first_ns = min(voxel.first_ns, frame.t_ns)
        voxel.last_ns = max(voxel.last_ns, frame.t_ns)
    elif not voxel.frames:
        voxel.first_ns = frame.t_ns
        voxel.last_ns = frame.t_ns
    voxel.frames.add(frame.frame_id)
    voxel.masks.add(detection.mask_id)
    if detection.track_id is not None:
        voxel.tracks.add(detection.track_id)
    voxel.labels[detection.label] = voxel.labels.get(detection.label, 0.0) + max(rank, 0.0)
    if rank >= voxel.best_weight:
        voxel.best_weight = rank
        voxel.best_frame_id = frame.frame_id
        voxel.best_box = detection.box_xyxy
        voxel.source = frame.source
        voxel.model_id = frame.model_id


def _voxel_key(point: Vec3, voxel_m: float) -> tuple[int, int, int]:
    return (
        math.floor(point.x / voxel_m),
        math.floor(point.y / voxel_m),
        math.floor(point.z / voxel_m),
    )


def _cluster(voxels: Sequence[_Voxel], eps_m: float, min_points: int) -> list[list[_Voxel]]:
    count = len(voxels)
    neighbors: list[list[int]] = []
    for left in range(count):
        found: list[int] = []
        for right in range(count):
            if _distance(voxels[left].centroid, voxels[right].centroid) <= eps_m:
                found.append(right)
        neighbors.append(found)
    labels = [-1] * count
    cluster_id = 0
    for index in range(count):
        if labels[index] != -1 or len(neighbors[index]) < min_points:
            continue
        labels[index] = cluster_id
        stack = list(neighbors[index])
        while stack:
            cursor = stack.pop()
            if labels[cursor] == -1:
                labels[cursor] = cluster_id
            if len(neighbors[cursor]) >= min_points:
                for neighbor in neighbors[cursor]:
                    if labels[neighbor] == -1:
                        stack.append(neighbor)
        cluster_id += 1
    groups: dict[int, list[_Voxel]] = {}
    for index, label in enumerate(labels):
        if label >= 0:
            groups.setdefault(label, []).append(voxels[index])
    return list(groups.values())


def _landmark(group: Sequence[_Voxel], map_frame: str, number: int) -> BenchLandmark | None:
    total = sum(voxel.count for voxel in group)
    if total <= 0:
        return None
    centroid = Vec3(
        sum(voxel.sum_x for voxel in group) / total,
        sum(voxel.sum_y for voxel in group) / total,
        sum(voxel.sum_z for voxel in group) / total,
    )
    frames: set[int] = set()
    masks: set[str] = set()
    tracks: set[int] = set()
    labels: dict[str, float] = {}
    best = max(group, key=lambda voxel: voxel.best_weight)
    log_odds = sum(voxel.log_odds for voxel in group) / len(group)
    first_ns = min(voxel.first_ns for voxel in group)
    last_ns = max(voxel.last_ns for voxel in group)
    for voxel in group:
        frames.update(voxel.frames)
        masks.update(voxel.masks)
        tracks.update(voxel.tracks)
        for name, weight in voxel.labels.items():
            labels[name] = labels.get(name, 0.0) + weight
    label = max(labels, key=lambda name: (labels[name], name)) if labels else "object"
    return BenchLandmark(
        landmark_id=f"lm-{number}",
        centroid=centroid,
        map_frame=map_frame,
        frame_ids=tuple(sorted(frames)),
        mask_ids=tuple(sorted(masks)),
        track_ids=tuple(sorted(tracks)),
        label=label,
        description="",
        confidence=_sigmoid(log_odds),
        provider="",
        model_id="",
        prompt_version="unlabelled",
        first_seen_ns=first_ns,
        last_seen_ns=last_ns,
        observation_count=len(frames),
        best_frame_id=best.best_frame_id,
        best_box_xyxy=best.best_box,
        sam_source=best.source,
        sam_model_id=best.model_id,
    )


def _with_label(landmark: BenchLandmark, labelled: ObjectLabel, provider: str) -> BenchLandmark:
    confidence = landmark.confidence if labelled.confidence is None else labelled.confidence
    return replace(
        landmark,
        label=labelled.label,
        description=labelled.description,
        confidence=confidence,
        provider=provider,
        model_id=labelled.model_id,
        prompt_version="muse-crop-v1",
    )


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    natural = math.exp(value)
    return natural / (1.0 + natural)


def _distance(left: Vec3, right: Vec3) -> float:
    return math.sqrt((left.x - right.x) ** 2 + (left.y - right.y) ** 2 + (left.z - right.z) ** 2)


def edge_distance_px(mask: BoolMask) -> NDArray[np.float64]:
    """City-block distance from each pixel to the mask boundary.

    Pixels outside the mask stay large. A boundary pixel is 0, so the
    evidence weight falls to the edge floor there.
    """
    height, width = mask.shape
    boundary = mask_boundary(mask)
    infinity = float(height + width + 1)
    distance = np.full((height, width), infinity, dtype=np.float64)
    distance[boundary] = 0.0
    for row in range(height):
        for column in range(width):
            best = distance[row, column]
            if row > 0:
                best = min(best, distance[row - 1, column] + 1.0)
            if column > 0:
                best = min(best, distance[row, column - 1] + 1.0)
            distance[row, column] = best
    for row in range(height - 1, -1, -1):
        for column in range(width - 1, -1, -1):
            best = distance[row, column]
            if row + 1 < height:
                best = min(best, distance[row + 1, column] + 1.0)
            if column + 1 < width:
                best = min(best, distance[row, column + 1] + 1.0)
            distance[row, column] = best
    outside = ~mask
    distance[outside] = infinity
    # A one-pixel mask is its own boundary. Keep that 0.
    distance[boundary] = 0.0
    return distance
