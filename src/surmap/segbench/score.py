"""Per-frame mask scores, 3D survivor scores, and what a route cost.

3D survivor recall reuses `score_survivors` at the scoring frame's match
radius (3 m unless the bench says otherwise). Positions are whatever
frame the landmarks and the truth already share; the report names it.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from surmap.mission.metrics import SurvivorDetection, score_survivors
from surmap.segbench.conventions import ScoringFrame, is_survivor_label
from surmap.segbench.dataset import BenchDataset, BenchFrame, read_label_image
from surmap.segbench.fusion import BenchLandmark
from surmap.segbench.masks import (
    BoolMask,
    boundary_f1,
    match_instances,
    pixel_precision_recall,
    rasterize_polygon,
)
from surmap.segbench.routes import RouteObservation
from surmap.simulation.disaster_world import (
    DisasterGroundTruth,
    MapEnu,
    PersonGroundTruth,
)
from surmap.types import Vec3


@dataclass(frozen=True)
class PriceRow:
    """Dollars for one provider. Unset prices are zero, not a guessed invoice."""

    usd_per_million_input_tokens: float = 0.0
    usd_per_million_output_tokens: float = 0.0
    usd_per_gpu_second: float = 0.0


@dataclass(frozen=True)
class SurvivorTruth:
    """One person in the scoring map frame."""

    id: str
    xyz: Vec3


@dataclass(frozen=True)
class FrameScore:
    """Mask scores for one frame."""

    frame_id: int
    mean_iou: float
    boundary_f1: float
    pixel_precision: float
    pixel_recall: float
    survivor_recall: float | None
    false_positives: int


@dataclass(frozen=True)
class BenchReport:
    """One route, scored offline."""

    route: str
    scoring: ScoringFrame
    frames: tuple[FrameScore, ...]
    mean_iou: float
    mean_boundary_f1: float
    mean_pixel_precision: float
    mean_pixel_recall: float
    survivor_instance_recall: float | None
    false_positives_per_frame: float
    found: int
    total: int
    mean_position_error_m: float | None
    false_positive_landmarks: int
    time_to_first_detection_s: float | None
    latency_p50_s: float | None
    latency_p95_s: float | None
    input_tokens: int
    output_tokens: int
    gpu_seconds: float
    cost_usd: float
    cost_per_frame_usd: float


def load_prices(path: Path | None) -> dict[str, PriceRow]:
    """Read a price table. A missing file means every route costs zero."""
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("price table must be an object")
    prices: dict[str, PriceRow] = {}
    for key, value in payload.items():
        if not isinstance(value, dict):
            raise ValueError(f"price for {key} must be an object")
        body = {str(name): item for name, item in value.items()}
        prices[str(key)] = PriceRow(
            usd_per_million_input_tokens=_price(body, "usd_per_million_input_tokens"),
            usd_per_million_output_tokens=_price(body, "usd_per_million_output_tokens"),
            usd_per_gpu_second=_price(body, "usd_per_gpu_second"),
        )
    return prices


def load_people(path: Path) -> tuple[SurvivorTruth, ...]:
    """Read `[{"id", "x", "y", "z"}]` in the scoring map frame."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("people file must be a list")
    people: list[SurvivorTruth] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"person {index} must be an object")
        body = {str(key): value for key, value in item.items()}
        name = body.get("id")
        if not isinstance(name, str) or not name:
            raise ValueError(f"person {index} id must be text")
        people.append(
            SurvivorTruth(
                name,
                Vec3(
                    _number(body.get("x"), "x"),
                    _number(body.get("y"), "y"),
                    _number(body.get("z"), "z"),
                ),
            )
        )
    return tuple(people)


def people_from_disaster(truth: DisasterGroundTruth) -> tuple[SurvivorTruth, ...]:
    """The disaster-block people, in map ENU."""
    return tuple(
        SurvivorTruth(person.id, Vec3(person.map_enu.x_m, person.map_enu.y_m, person.map_enu.z_m))
        for person in truth.people
    )


def percentile(values: Sequence[float], fraction: float) -> float:
    """Linear percentile. `fraction` 0.5 is the median of the sorted values."""
    if not values:
        raise ValueError("percentile of an empty series is undefined")
    if fraction < 0 or fraction > 1:
        raise ValueError("percentile fraction must lie in [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = fraction * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def score_bench(
    dataset: BenchDataset,
    observations: Sequence[RouteObservation],
    landmarks: Sequence[BenchLandmark],
    people: Sequence[SurvivorTruth],
    prices: Mapping[str, PriceRow],
    *,
    route: str,
    mission_start_ns: int | None = None,
) -> BenchReport:
    """Score one route. Nothing here contacts a model."""
    by_frame = {item.frame_id: item for item in observations}
    frame_scores = tuple(
        _score_frame(frame, by_frame.get(frame.frame_id), dataset.classes)
        for frame in dataset.frames
    )
    recalls = [item.survivor_recall for item in frame_scores if item.survivor_recall is not None]
    start_ns = (
        mission_start_ns
        if mission_start_ns is not None
        else min((frame.t_ns for frame in dataset.frames), default=0)
    )
    impact = score_survivors(
        _as_disaster(people),
        tuple(
            SurvivorDetection(landmark.centroid, landmark.first_seen_ns, landmark.label)
            for landmark in landmarks
            if is_survivor_label(landmark.label)
        ),
        mission_start_ns=start_ns,
        match_radius_m=dataset.scoring.match_radius_m,
        basis="segbench",
    )
    survivor_landmarks = [landmark for landmark in landmarks if is_survivor_label(landmark.label)]
    latencies = [item.latency_s for item in observations]
    tokens_in = sum(item.input_tokens for item in observations)
    tokens_out = sum(item.output_tokens for item in observations)
    gpu_seconds = sum(item.gpu_seconds for item in observations)
    cost = _cost(observations, prices)
    count = len(dataset.frames)
    return BenchReport(
        route=route,
        scoring=dataset.scoring,
        frames=frame_scores,
        mean_iou=_mean(item.mean_iou for item in frame_scores),
        mean_boundary_f1=_mean(item.boundary_f1 for item in frame_scores),
        mean_pixel_precision=_mean(item.pixel_precision for item in frame_scores),
        mean_pixel_recall=_mean(item.pixel_recall for item in frame_scores),
        survivor_instance_recall=(sum(recalls) / len(recalls)) if recalls else None,
        false_positives_per_frame=_mean(float(item.false_positives) for item in frame_scores),
        found=impact.found,
        total=impact.total,
        mean_position_error_m=impact.mean_position_error_m,
        false_positive_landmarks=len(survivor_landmarks) - impact.found,
        time_to_first_detection_s=impact.time_to_first_detection_s,
        latency_p50_s=percentile(latencies, 0.5) if latencies else None,
        latency_p95_s=percentile(latencies, 0.95) if latencies else None,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        gpu_seconds=gpu_seconds,
        cost_usd=cost,
        cost_per_frame_usd=(cost / count) if count else 0.0,
    )


def _score_frame(
    frame: BenchFrame,
    observation: RouteObservation | None,
    classes: Mapping[int, str],
) -> FrameScore:
    width = frame.intrinsics.width
    height = frame.intrinsics.height
    truths, class_ids = _truth_masks(frame)
    predictions = _prediction_masks(observation, width, height)
    matches = match_instances(predictions, truths, min_iou=0.5)
    matched_pred = {match.pred_index for match in matches}
    matched_truth = {match.gt_index for match in matches}
    ious = [match.iou for match in matches]
    ious.extend(0.0 for _ in range(len(predictions) - len(matched_pred)))
    ious.extend(0.0 for _ in range(len(truths) - len(matched_truth)))
    mean_iou = 1.0 if not ious else sum(ious) / len(ious)
    predicted_union = _union(predictions, height, width)
    truth_union = _union(truths, height, width)
    precision, recall = pixel_precision_recall(predicted_union, truth_union)
    survivor_indexes = [
        index
        for index, class_id in enumerate(class_ids)
        if is_survivor_label(classes.get(class_id, ""))
    ]
    survivor_recall = None
    if survivor_indexes:
        hits = sum(1 for index in survivor_indexes if index in matched_truth)
        survivor_recall = hits / len(survivor_indexes)
    return FrameScore(
        frame_id=frame.frame_id,
        mean_iou=mean_iou,
        boundary_f1=boundary_f1(predicted_union, truth_union),
        pixel_precision=precision,
        pixel_recall=recall,
        survivor_recall=survivor_recall,
        false_positives=len(predictions) - len(matched_pred),
    )


def _truth_masks(frame: BenchFrame) -> tuple[list[BoolMask], list[int]]:
    instance = read_label_image(frame.instance_mask_path)
    class_image = read_label_image(frame.class_mask_path)
    masks: list[BoolMask] = []
    class_ids: list[int] = []
    for instance_id in sorted(int(value) for value in np.unique(instance)):
        if instance_id == 0:
            continue
        region = instance == instance_id
        classes, counts = np.unique(class_image[region], return_counts=True)
        class_ids.append(int(classes[int(np.argmax(counts))]))
        masks.append(region)
    return masks, class_ids


def _prediction_masks(
    observation: RouteObservation | None,
    width: int,
    height: int,
) -> list[BoolMask]:
    if observation is None:
        return []
    return [
        rasterize_polygon(detection.mask_polygon, width, height)
        for detection in observation.detections
    ]


def _union(masks: Sequence[BoolMask], height: int, width: int) -> BoolMask:
    canvas = np.zeros((height, width), dtype=np.bool_)
    for mask in masks:
        canvas |= mask
    return canvas


def _as_disaster(people: Sequence[SurvivorTruth]) -> DisasterGroundTruth:
    return DisasterGroundTruth(
        world="segbench",
        people=tuple(
            PersonGroundTruth(
                id=person.id,
                pose="standing",
                map_enu=MapEnu(person.xyz.x, person.xyz.y, person.xyz.z),
                yaw_rad=0.0,
                latitude_deg=0.0,
                longitude_deg=0.0,
                altitude_m=person.xyz.z,
            )
            for person in people
        ),
        roads=(),
        latitude_deg=0.0,
        longitude_deg=0.0,
        elevation_m=0.0,
        heading_deg=0.0,
        world_frame_orientation="ENU",
        surface_model="bench",
    )


def _cost(observations: Sequence[RouteObservation], prices: Mapping[str, PriceRow]) -> float:
    total = 0.0
    for item in observations:
        price = prices.get(item.source, PriceRow())
        total += item.input_tokens / 1_000_000 * price.usd_per_million_input_tokens
        total += item.output_tokens / 1_000_000 * price.usd_per_million_output_tokens
        total += item.gpu_seconds * price.usd_per_gpu_second
    return total


def _mean(values: Iterable[float]) -> float:
    series = [float(item) for item in values]
    if not series:
        return 0.0
    return sum(series) / len(series)


def _price(body: dict[str, object], key: str) -> float:
    if key not in body:
        return 0.0
    return _number(body[key], key)


def _number(raw: object, where: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ValueError(f"{where} must be a number")
    return float(raw)
