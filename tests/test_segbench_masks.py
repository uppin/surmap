"""Mask raster, overlap, boundary F1, and Hungarian instance matching."""

from __future__ import annotations

import numpy as np

from surmap.segbench.masks import (
    assign_maximum,
    boundary_f1,
    intersection_over_union,
    match_instances,
    pixel_precision_recall,
    rasterize_polygon,
)


def test_a_polygon_raster_covers_its_interior_and_an_empty_ring_covers_nothing() -> None:
    # Given a rectangle and a ring that is not a polygon
    rectangle = ((1.0, 1.0), (5.0, 1.0), (5.0, 4.0), (1.0, 4.0))

    # When both are rasterised onto the same frame
    filled = rasterize_polygon(rectangle, 8, 6)
    empty = rasterize_polygon(((1.0, 1.0), (2.0, 2.0)), 8, 6)

    # Then the rectangle claims its interior and the short ring claims nothing
    assert filled[2, 2]
    assert not filled[0, 0]
    assert int(empty.sum()) == 0


def test_identical_masks_score_perfect_overlap_and_two_empty_masks_score_one() -> None:
    # Given two copies of one blob, and two empty frames
    blob = np.zeros((4, 4), dtype=np.bool_)
    blob[1:3, 1:3] = True
    blank = np.zeros((4, 4), dtype=np.bool_)

    # When overlap, pixels, and the boundary are scored
    overlap = intersection_over_union(blob, blob)
    precision, recall = pixel_precision_recall(blob, blob)
    boundary = boundary_f1(blob, blob)
    empty_overlap = intersection_over_union(blank, blank)

    # Then a copy is a perfect match and emptiness is not a miss
    assert overlap == 1.0
    assert precision == 1.0
    assert recall == 1.0
    assert boundary == 1.0
    assert empty_overlap == 1.0


def test_a_shifted_mask_loses_pixel_precision_and_keeps_a_tolerant_boundary() -> None:
    # Given a block and the same block shifted by one pixel
    truth = np.zeros((6, 6), dtype=np.bool_)
    prediction = np.zeros((6, 6), dtype=np.bool_)
    truth[1:4, 1:4] = True
    prediction[1:4, 2:5] = True

    # When pixel scores and a 1 px boundary tolerance are computed
    precision, recall = pixel_precision_recall(prediction, truth)
    exact_boundary = boundary_f1(prediction, truth, tolerance_px=0)
    tolerant_boundary = boundary_f1(prediction, truth, tolerance_px=1)

    # Then the pixels only partly agree, and the nearby boundary still matches
    assert precision < 1.0
    assert recall < 1.0
    assert exact_boundary < tolerant_boundary


def test_hungarian_matching_keeps_the_overlap_at_or_above_one_half() -> None:
    # Given one truth blob, a copy of it, and a shift whose IoU is below one half
    truth = np.zeros((6, 8), dtype=np.bool_)
    truth[0:4, 0:4] = True
    copy = truth.copy()
    shifted = np.zeros((6, 8), dtype=np.bool_)
    shifted[0:4, 2:6] = True

    # When the two predictions are matched to that truth
    matches = match_instances((shifted, copy), (truth,), min_iou=0.5)

    # Then only the copy is kept, and it is the second prediction
    assert len(matches) == 1
    assert matches[0].pred_index == 1
    assert matches[0].gt_index == 0
    assert matches[0].iou == 1.0


def test_maximum_weight_assignment_prefers_the_heavier_pairing() -> None:
    # Given weights where the heavy diagonal sums to more than the cross
    weights = ((5.0, 1.0), (1.0, 4.0))

    # When the maximum-weight assignment is solved
    pairs = assign_maximum(weights)

    # Then each row takes its heavier column
    assert set(pairs) == {(0, 0), (1, 1)}
