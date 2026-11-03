"""Object summaries and neighbours."""

from __future__ import annotations

import numpy as np
import pytest

from surmap.objects3d import (
    Relation,
    ShapeClass,
    neighbours,
    summarize,
)
from tests.object_fakes import (
    a_box,
    a_plane,
    a_pole,
    a_square,
    a_summarised_box,
    ids,
    is_within,
    relations,
    spans,
    two_triangles,
    yaw_of_longest_axis_deg,
)

# --- summary ---------------------------------------------------------------------------------


def test_a_rotated_box_summarises_to_its_centroid() -> None:
    # Given a 4 x 2 x 1 m box centred at (10, 5, 1), yawed 30 degrees
    points = a_box(centre=(10.0, 5.0, 1.0), yaw_deg=30.0)

    # When it is summarised
    summary = summarize("obj_1", "box", points, frame="map", up_axis="+z")

    # Then its centroid is the box centre
    assert is_within(summary.centroid, (10.0, 5.0, 1.0), metres=0.01)


def test_a_rotated_box_summarises_to_its_extents_within_a_centimetre() -> None:
    # Given a 4 x 2 x 1 m box yawed 30 degrees
    points = a_box(centre=(10.0, 5.0, 1.0), half=(2.0, 1.0, 0.5), yaw_deg=30.0)

    # When it is summarised
    summary = summarize("obj_1", "box", points, frame="map", up_axis="+z")

    # Then the oriented box has its half-lengths, largest first
    assert is_within(summary.obb.extents, (2.0, 1.0, 0.5), metres=0.01)


def test_a_rotated_box_summarises_to_its_yaw_within_a_degree() -> None:
    # Given a box whose long side is yawed 30 degrees about +z
    points = a_box(centre=(10.0, 5.0, 1.0), yaw_deg=30.0)

    # When it is summarised
    summary = summarize("obj_1", "box", points, frame="map", up_axis="+z")

    # Then the oriented box's longest axis points along 30 degrees
    assert yaw_of_longest_axis_deg(summary.obb) == pytest.approx(30.0, abs=1.0)


def test_a_box_is_volumetric() -> None:
    # Given a solid box
    points = a_box(yaw_deg=30.0)

    # When it is summarised
    summary = summarize("obj_1", "box", points, frame="map", up_axis="+z")

    # Then it reads as extended in all three axes
    assert summary.shape is ShapeClass.VOLUMETRIC


def test_a_flat_patch_is_planar() -> None:
    # Given a 3 x 2 m patch only millimetres thick
    points = a_plane()

    # When it is summarised
    summary = summarize("obj_2", "sign", points, frame="map", up_axis="+z")

    # Then it reads as flat
    assert summary.shape is ShapeClass.PLANAR


def test_a_pole_is_linear() -> None:
    # Given a 4 m pole 10 cm across
    points = a_pole()

    # When it is summarised
    summary = summarize("obj_3", "pole", points, frame="map", up_axis="+z")

    # Then it reads as long and thin
    assert summary.shape is ShapeClass.LINEAR


def test_height_runs_along_minus_y_in_the_demo_map() -> None:
    # Given a 4 m wide, 1.8 m tall, 2 m deep box in the y-down demo map
    points = a_box(centre=(0.0, -0.9, 0.0), half=(2.0, 0.9, 1.0))

    # When it is summarised with -y as up
    summary = summarize("obj_4", "car", points, frame="map", up_axis="-y")

    # Then its height is the y extent
    assert summary.height_m == pytest.approx(1.8, abs=0.01)


def test_footprint_lies_on_the_x_z_plane_when_minus_y_is_up() -> None:
    # Given a 4 m wide, 1.8 m tall, 2 m deep box in the y-down demo map
    points = a_box(centre=(0.0, -0.9, 0.0), half=(2.0, 0.9, 1.0))

    # When it is summarised with -y as up
    summary = summarize("obj_4", "car", points, frame="map", up_axis="-y")

    # Then its footprint is width times depth
    assert summary.footprint_m2 == pytest.approx(8.0, abs=0.05)


def test_the_same_box_is_measured_along_z_when_plus_z_is_up() -> None:
    # Given the same box, read as an ENU snapshot
    points = a_box(centre=(0.0, -0.9, 0.0), half=(2.0, 0.9, 1.0))

    # When it is summarised with +z as up
    summary = summarize("obj_4", "car", points, frame="map", up_axis="+z")

    # Then its height is the z extent
    assert summary.height_m == pytest.approx(2.0, abs=0.01)


def test_a_summary_states_its_frame_up_axis_and_units() -> None:
    # Given a box in the demo map
    points = a_box()

    # When it is summarised
    summary = summarize("obj_5", "box", points, frame="map", up_axis="-y")

    # Then it names where its coordinates live
    assert (summary.frame, summary.up_axis, summary.units) == ("map", "-y", "m")


def test_a_summary_carries_the_axis_aligned_box_of_its_points() -> None:
    # Given an axis-aligned 4 x 2 x 1 m box centred at (10, 5, 1)
    points = a_box(centre=(10.0, 5.0, 1.0))

    # When it is summarised
    summary = summarize("obj_5", "box", points, frame="map", up_axis="+z")

    # Then its AABB spans the box
    assert spans(summary.aabb_min, summary.aabb_max, (8.0, 4.0, 0.5), (12.0, 6.0, 1.5))


def test_a_mesh_summary_counts_its_points_and_faces() -> None:
    # Given a two-triangle square
    points, faces = a_square(), two_triangles()

    # When it is summarised with its faces
    summary = summarize("obj_6", "panel", points, frame="map", up_axis="-y", faces=faces)

    # Then it counts four points and two faces
    assert (summary.n_points, summary.n_faces) == (4, 2)


def test_a_summary_has_no_neighbours_until_they_are_computed() -> None:
    # Given a box
    points = a_box()

    # When it is summarised on its own
    summary = summarize("obj_7", "box", points, frame="map", up_axis="+z")

    # Then it lists nobody near it
    assert summary.neighbours == ()


def test_an_empty_point_set_cannot_be_summarised() -> None:
    # Given no points at all
    points = np.zeros((0, 3), dtype=np.float32)

    # When / Then summarising it is refused
    with pytest.raises(ValueError):
        summarize("obj_8", "nothing", points, frame="map", up_axis="+z")


def test_a_point_set_that_is_not_n_by_3_cannot_be_summarised() -> None:
    # Given 2D points
    points = np.zeros((10, 2), dtype=np.float32)

    # When / Then summarising it is refused
    with pytest.raises(ValueError):
        summarize("obj_9", "flat", points, frame="map", up_axis="+z")


# --- neighbours ------------------------------------------------------------------------------


def test_a_box_resting_on_another_reads_above() -> None:
    # Given a small box sitting 1 cm over a 1 m cube
    bottom = a_summarised_box("bottom", centre=(0.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    top = a_summarised_box("top", centre=(0.0, 0.0, 1.26), half=(0.3, 0.3, 0.25))

    # When the cube's neighbours are found
    found = neighbours(bottom, [top])

    # Then the small box sits above it
    assert relations(found) == [Relation.ABOVE]


def test_the_box_underneath_reads_below() -> None:
    # Given a small box sitting 1 cm over a 1 m cube
    bottom = a_summarised_box("bottom", centre=(0.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    top = a_summarised_box("top", centre=(0.0, 0.0, 1.26), half=(0.3, 0.3, 0.25))

    # When the small box's neighbours are found
    found = neighbours(top, [bottom])

    # Then the cube sits below it
    assert relations(found) == [Relation.BELOW]


def test_above_follows_minus_y_in_the_demo_map() -> None:
    # Given, in the y-down demo map, a box whose y is 1 cm more negative than a cube's top
    bottom = a_summarised_box("bottom", centre=(0.0, -0.5, 0.0), half=(0.5, 0.5, 0.5), up_axis="-y")
    top = a_summarised_box("top", centre=(0.0, -1.26, 0.0), half=(0.3, 0.25, 0.3), up_axis="-y")

    # When the cube's neighbours are found
    found = neighbours(bottom, [top])

    # Then the box sits above it
    assert relations(found) == [Relation.ABOVE]


def test_boxes_side_by_side_read_next_to() -> None:
    # Given two 1 m cubes on the ground 70 cm apart
    left = a_summarised_box("left", centre=(0.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    right = a_summarised_box("right", centre=(1.7, 0.0, 0.5), half=(0.5, 0.5, 0.5))

    # When the left cube's neighbours are found
    found = neighbours(left, [right])

    # Then the right cube is next to it
    assert relations(found) == [Relation.NEXT_TO]


def test_a_neighbour_distance_is_the_gap_between_the_boxes() -> None:
    # Given two 1 m cubes on the ground 70 cm apart
    left = a_summarised_box("left", centre=(0.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    right = a_summarised_box("right", centre=(1.7, 0.0, 0.5), half=(0.5, 0.5, 0.5))

    # When the left cube's neighbours are found
    found = neighbours(left, [right])

    # Then the right cube is 70 cm away
    assert found[0].distance_m == pytest.approx(0.7, abs=0.01)


def test_interpenetrating_boxes_read_overlaps() -> None:
    # Given two 1 m cubes sharing half their volume
    one = a_summarised_box("one", centre=(0.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    other = a_summarised_box("other", centre=(0.5, 0.0, 0.5), half=(0.5, 0.5, 0.5))

    # When the first cube's neighbours are found
    found = neighbours(one, [other])

    # Then the second one overlaps it
    assert relations(found) == [Relation.OVERLAPS]


def test_neighbours_are_listed_nearest_first() -> None:
    # Given cubes 3 m and 70 cm away from a cube at the origin
    here = a_summarised_box("here", centre=(0.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    far = a_summarised_box("far", centre=(4.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    near = a_summarised_box("near", centre=(1.7, 0.0, 0.5), half=(0.5, 0.5, 0.5))

    # When its neighbours are found
    found = neighbours(here, [far, near])

    # Then the nearer cube comes first
    assert ids(found) == ["near", "far"]


def test_an_object_is_not_its_own_neighbour() -> None:
    # Given a cube listed among the others alongside one real neighbour
    here = a_summarised_box("here", centre=(0.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    near = a_summarised_box("near", centre=(1.7, 0.0, 0.5), half=(0.5, 0.5, 0.5))

    # When its neighbours are found
    found = neighbours(here, [here, near])

    # Then only the other cube is listed
    assert ids(found) == ["near"]


def test_objects_beyond_the_search_distance_are_not_neighbours() -> None:
    # Given a cube 9 m from the one at the origin
    here = a_summarised_box("here", centre=(0.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    distant = a_summarised_box("distant", centre=(10.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))

    # When neighbours within 5 m are found
    found = neighbours(here, [distant], max_distance_m=5.0)

    # Then there are none
    assert found == ()


def test_neighbours_stop_at_the_limit() -> None:
    # Given three cubes in a row beside the one at the origin
    here = a_summarised_box("here", centre=(0.0, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    a = a_summarised_box("a", centre=(1.2, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    b = a_summarised_box("b", centre=(2.4, 0.0, 0.5), half=(0.5, 0.5, 0.5))
    c = a_summarised_box("c", centre=(3.6, 0.0, 0.5), half=(0.5, 0.5, 0.5))

    # When at most two neighbours are asked for
    found = neighbours(here, [a, b, c], limit=2)

    # Then the two nearest are listed
    assert ids(found) == ["a", "b"]
