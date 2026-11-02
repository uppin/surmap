"""Polygon masks: raster, overlap, boundary, and instance matching.

SAM outlines stay polygons (`mask_outline`). These helpers turn a ring
into pixels in the frame named by the scoring conventions, then compare
it with a ground-truth instance mask.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

BoolMask = NDArray[np.bool_]


@dataclass(frozen=True)
class InstanceMatch:
    """One predicted instance paired with one ground-truth instance."""

    pred_index: int
    gt_index: int
    iou: float


def rasterize_polygon(
    polygon: Sequence[tuple[float, float]],
    width: int,
    height: int,
) -> BoolMask:
    """Fill `polygon` on a height-by-width boolean image.

    A ring with fewer than three vertices claims no pixels. Coordinates
    are pixels in the same space as `width` and `height`.
    """
    if width < 0 or height < 0:
        raise ValueError("mask size must be non-negative")
    canvas = np.zeros((height, width), dtype=np.bool_)
    if len(polygon) < 3 or width == 0 or height == 0:
        return canvas
    image = Image.new("L", (width, height), 0)
    ImageDraw.Draw(image).polygon([(float(x), float(y)) for x, y in polygon], fill=1)
    painted = cast("NDArray[np.uint8]", np.asarray(image, dtype=np.uint8))
    return painted > 0


def intersection_over_union(prediction: BoolMask, truth: BoolMask) -> float:
    """Intersection over union. Two empty masks score 1."""
    _same_shape(prediction, truth)
    intersection = int(np.logical_and(prediction, truth).sum())
    union = int(np.logical_or(prediction, truth).sum())
    if union == 0:
        return 1.0
    return intersection / union


def pixel_precision_recall(prediction: BoolMask, truth: BoolMask) -> tuple[float, float]:
    """Pixel precision and recall. An empty pair scores (1, 1)."""
    _same_shape(prediction, truth)
    true_positive = int(np.logical_and(prediction, truth).sum())
    false_positive = int(np.logical_and(prediction, ~truth).sum())
    false_negative = int(np.logical_and(~prediction, truth).sum())
    precision = (
        1.0
        if true_positive + false_positive == 0
        else true_positive / (true_positive + false_positive)
    )
    recall = (
        1.0
        if true_positive + false_negative == 0
        else true_positive / (true_positive + false_negative)
    )
    return precision, recall


def mask_boundary(mask: BoolMask) -> BoolMask:
    """True where a mask pixel touches the outside, including the image edge."""
    if mask.size == 0:
        return mask.copy()
    padded = np.pad(mask, 1, constant_values=False)
    center = padded[1:-1, 1:-1]
    neighbors = padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    return center & ~neighbors


def dilate(mask: BoolMask, radius_px: int) -> BoolMask:
    """Square dilation. `radius_px` of 0 returns the same pixels."""
    if radius_px < 0:
        raise ValueError("dilation radius must be non-negative")
    if radius_px == 0 or mask.size == 0:
        return mask.copy()
    height, width = mask.shape
    grown = np.zeros_like(mask)
    for dy in range(-radius_px, radius_px + 1):
        for dx in range(-radius_px, radius_px + 1):
            src_y = slice(max(0, -dy), min(height, height - dy))
            dst_y = slice(max(0, dy), min(height, height + dy))
            src_x = slice(max(0, -dx), min(width, width - dx))
            dst_x = slice(max(0, dx), min(width, width + dx))
            grown[dst_y, dst_x] |= mask[src_y, src_x]
    return grown


def boundary_f1(prediction: BoolMask, truth: BoolMask, *, tolerance_px: int = 2) -> float:
    """Boundary F1. A boundary pixel matches when it lies within `tolerance_px`."""
    _same_shape(prediction, truth)
    if tolerance_px < 0:
        raise ValueError("boundary tolerance must be non-negative")
    if not prediction.any() and not truth.any():
        return 1.0
    predicted_edge = mask_boundary(prediction)
    truth_edge = mask_boundary(truth)
    if not predicted_edge.any() and not truth_edge.any():
        return 1.0
    precision = _ratio(
        int(np.logical_and(predicted_edge, dilate(truth_edge, tolerance_px)).sum()),
        int(predicted_edge.sum()),
    )
    recall = _ratio(
        int(np.logical_and(truth_edge, dilate(predicted_edge, tolerance_px)).sum()),
        int(truth_edge.sum()),
    )
    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def match_instances(
    predictions: Sequence[BoolMask],
    truths: Sequence[BoolMask],
    *,
    min_iou: float = 0.5,
) -> tuple[InstanceMatch, ...]:
    """Hungarian matching. A pair is kept only when its IoU is at least `min_iou`."""
    if min_iou < 0 or min_iou > 1:
        raise ValueError("min_iou must lie in [0, 1]")
    if not predictions or not truths:
        return ()
    weights = [
        [intersection_over_union(prediction, truth) for truth in truths]
        for prediction in predictions
    ]
    pairs = assign_maximum(weights)
    kept = [
        InstanceMatch(row, column, weights[row][column])
        for row, column in pairs
        if weights[row][column] >= min_iou
    ]
    kept.sort(key=lambda match: (match.gt_index, match.pred_index))
    return tuple(kept)


def assign_maximum(weights: Sequence[Sequence[float]]) -> tuple[tuple[int, int], ...]:
    """Maximum-weight bipartite matching. Unmatched rows and columns are allowed."""
    row_count = len(weights)
    if row_count == 0:
        return ()
    column_count = len(weights[0])
    if column_count == 0:
        return ()
    if any(len(row) != column_count for row in weights):
        raise ValueError("weight rows must be the same length")
    size = max(row_count, column_count)
    cost = [[0.0] * size for _ in range(size)]
    for row in range(row_count):
        for column in range(column_count):
            weight = float(weights[row][column])
            if not math.isfinite(weight):
                raise ValueError("weights must be finite")
            cost[row][column] = -weight
    assignment = _hungarian_minimize(cost)
    return tuple(
        (row, column) for row, column in assignment if row < row_count and column < column_count
    )


def _hungarian_minimize(cost: list[list[float]]) -> tuple[tuple[int, int], ...]:
    """Kuhn–Munkres minimum-cost assignment on a square matrix."""
    size = len(cost)
    infinity = float("inf")
    dual_row = [0.0] * (size + 1)
    dual_column = [0.0] * (size + 1)
    column_of = [0] * (size + 1)
    way = [0] * (size + 1)
    for row in range(1, size + 1):
        column_of[0] = row
        column = 0
        minimum = [infinity] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[column] = True
            current_row = column_of[column]
            delta = infinity
            next_column = 0
            for candidate in range(1, size + 1):
                if used[candidate]:
                    continue
                value = (
                    cost[current_row - 1][candidate - 1]
                    - dual_row[current_row]
                    - dual_column[candidate]
                )
                if value < minimum[candidate]:
                    minimum[candidate] = value
                    way[candidate] = column
                if minimum[candidate] < delta:
                    delta = minimum[candidate]
                    next_column = candidate
            for index in range(size + 1):
                if used[index]:
                    dual_row[column_of[index]] += delta
                    dual_column[index] -= delta
                else:
                    minimum[index] -= delta
            column = next_column
            if column_of[column] == 0:
                break
        while True:
            previous = way[column]
            column_of[column] = column_of[previous]
            column = previous
            if column == 0:
                break
    pairs: list[tuple[int, int]] = []
    for column in range(1, size + 1):
        row = column_of[column]
        if row != 0:
            pairs.append((row - 1, column - 1))
    return tuple(pairs)


def _same_shape(prediction: BoolMask, truth: BoolMask) -> None:
    if prediction.shape != truth.shape:
        raise ValueError(f"mask shapes differ: {prediction.shape} and {truth.shape}")


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0 if numerator == 0 else 0.0
    return numerator / denominator
