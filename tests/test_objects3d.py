"""The object 3D contract: summaries, `surmap-obj v1` text and GLB for agents.

Synthetic numpy fixtures only: box, plane and pole lattices or seeded-RNG clouds, a two-triangle
mesh. Every coordinate is metres in the named frame.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.objects3d import (
    Neighbour,
    Obb,
    ObjectSummary,
    Relation,
    ShapeClass,
    UpAxis,
    decode_obj_text,
    encode_obj_text,
    neighbours,
    read_glb_header,
    summarize,
    write_glb,
)

Vec3Tuple = tuple[float, float, float]

# --- builders --------------------------------------------------------------------------------


def a_box(
    centre: Vec3Tuple = (0.0, 0.0, 0.0),
    half: Vec3Tuple = (2.0, 1.0, 0.5),
    yaw_deg: float = 0.0,
    spacing: float = 0.1,
) -> NDArray[np.float32]:
    """A solid lattice box, yawed about +z, so its extents and axes are exact."""
    axes = [np.linspace(-h, h, round(2 * h / spacing) + 1) for h in half]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    yaw = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    cloud: NDArray[np.float32] = (grid @ yaw.T + np.array(centre)).astype(np.float32)
    return cloud


def a_plane(seed: int = 3) -> NDArray[np.float32]:
    """A 3 m x 2 m patch in the x-y plane with 3 mm of noise across it."""
    rng = np.random.default_rng(seed)
    xy = rng.uniform((-1.5, -1.0), (1.5, 1.0), size=(5_000, 2))
    z = rng.normal(0.0, 0.003, size=(5_000, 1))
    return np.hstack([xy, z]).astype(np.float32)


def a_pole(seed: int = 3) -> NDArray[np.float32]:
    """A 4 m tall pole of 5 cm radius standing on z = 0."""
    rng = np.random.default_rng(seed)
    angle = rng.uniform(0.0, 2 * math.pi, size=5_000)
    radius = 0.05 * np.sqrt(rng.uniform(0.0, 1.0, size=5_000))
    z = rng.uniform(0.0, 4.0, size=5_000)
    return np.stack([radius * np.cos(angle), radius * np.sin(angle), z], axis=1).astype(np.float32)


def a_noisy_box(n: int = 14_000, seed: int = 3) -> NDArray[np.float32]:
    """A car-sized cloud far from the map origin, with 1 cm of sensor noise."""
    rng = np.random.default_rng(seed)
    inside = rng.uniform((-2.0, -0.75, -1.0), (2.0, 0.75, 1.0), size=(n, 3))
    noise = rng.normal(0.0, 0.01, size=(n, 3))
    cloud: NDArray[np.float32] = (inside + noise + np.array((412.35, -88.10, 2.04))).astype(
        np.float32
    )
    return cloud


def a_square() -> NDArray[np.float32]:
    """Four corners of a 1 m square in the x-z plane around (412.35, -88.10, 2.04)."""
    offsets = np.array([(-0.5, 0.0, -0.5), (0.5, 0.0, -0.5), (0.5, 0.0, 0.5), (-0.5, 0.0, 0.5)])
    cloud: NDArray[np.float32] = (offsets + np.array((412.35, -88.10, 2.04))).astype(np.float32)
    return cloud


def two_triangles() -> NDArray[np.int32]:
    """The square split along its diagonal, 0-based."""
    return np.array([(0, 1, 2), (0, 2, 3)], dtype=np.int32)


def the_square_colours() -> NDArray[np.uint8]:
    return np.array([(158, 156, 153), (200, 10, 10), (10, 200, 10), (10, 10, 200)], dtype=np.uint8)


def a_summary_of(
    points: NDArray[np.float32],
    id: str = "obj_17",
    label: str = "car",
    up_axis: UpAxis = "-y",
) -> ObjectSummary:
    """A hand-built summary around the points' box — independent of `summarize`."""
    lo = tuple(float(v) for v in points.min(axis=0))
    hi = tuple(float(v) for v in points.max(axis=0))
    centre = tuple((a + b) / 2 for a, b in zip(lo, hi, strict=True))
    extents = tuple((b - a) / 2 for a, b in zip(lo, hi, strict=True))
    return ObjectSummary(
        id=id,
        label=label,
        confidence=0.9,
        frame="map",
        up_axis=up_axis,
        units="m",
        n_points=len(points),
        n_faces=0,
        centroid=_vec(points.mean(axis=0)),
        aabb_min=_vec(lo),
        aabb_max=_vec(hi),
        obb=Obb(
            centre=_vec(centre),
            extents=_vec(extents),
            rotation=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        ),
        height_m=0.0,
        footprint_m2=0.0,
        shape=ShapeClass.VOLUMETRIC,
        observed_frames=1,
        t_first_ns=None,
        t_last_ns=None,
        neighbours=(),
        geometry_uri=None,
    )


def a_summarised_box(
    id: str, centre: Vec3Tuple, half: Vec3Tuple, up_axis: UpAxis = "+z"
) -> ObjectSummary:
    return summarize(id, "box", a_box(centre, half), frame="map", up_axis=up_axis)


# --- matchers --------------------------------------------------------------------------------


def _vec(values: Sequence[float] | NDArray[np.floating[Any]]) -> Vec3Tuple:
    x, y, z = (float(v) for v in np.asarray(values, dtype=np.float64))
    return (x, y, z)


def is_within(actual: Vec3Tuple, expected: Vec3Tuple, metres: float) -> bool:
    return all(abs(a - e) <= metres for a, e in zip(actual, expected, strict=True))


def spans(lo: Vec3Tuple, hi: Vec3Tuple, expected_lo: Vec3Tuple, expected_hi: Vec3Tuple) -> bool:
    """Whether a min/max pair is the expected box, to a tenth of a millimetre."""
    return is_within(lo, expected_lo, metres=1e-4) and is_within(hi, expected_hi, metres=1e-4)


def yaw_of_longest_axis_deg(obb: Obb) -> float:
    """The heading of the box's first (longest) axis about +z, folded into [0, 180)."""
    x, y = obb.rotation[0][0], obb.rotation[1][0]
    return math.degrees(math.atan2(y, x)) % 180.0


def v_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("v ")]


def f_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("f ")]


def farthest_from(decoded: NDArray[np.float64], cloud: NDArray[np.float32]) -> float:
    """The largest distance from a decoded point to its nearest point in the cloud."""
    origin = cloud.astype(np.float64).mean(axis=0)
    a, b = decoded - origin, cloud.astype(np.float64) - origin
    squared = (a * a).sum(axis=1)[:, None] + (b * b).sum(axis=1)[None, :] - 2.0 * a @ b.T
    return float(math.sqrt(max(float(np.max(squared.min(axis=1))), 0.0)))


def relations(found: tuple[Neighbour, ...]) -> list[Relation]:
    return [n.relation for n in found]


def ids(found: tuple[Neighbour, ...]) -> list[str]:
    return [n.id for n in found]


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


# --- surmap-obj v1 text ----------------------------------------------------------------------


def test_a_dense_cloud_encodes_to_at_most_500_vertices() -> None:
    # Given a 14,000-point car-sized cloud
    points = a_noisy_box()

    # When it is encoded with the default limits
    text = encode_obj_text(a_summary_of(points), points)

    # Then the text carries no more than 500 vertices
    assert 0 < len(v_lines(text)) <= 500


def test_a_decimated_cloud_says_how_many_points_it_came_from() -> None:
    # Given a 14,000-point car-sized cloud
    points = a_noisy_box()

    # When it is encoded with the default limits
    text = encode_obj_text(a_summary_of(points), points)

    # Then the header records the original count
    assert "(decimated from 14000)" in text.splitlines()[1]


def test_a_decimated_cloud_decodes_within_a_centimetre_of_the_original_points() -> None:
    # Given a 14,000-point car-sized cloud far from the map origin
    points = a_noisy_box()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points))

    # Then every vertex lies within 1 cm of a real point
    assert farthest_from(decoded.points, points) <= 0.01


def test_encoding_the_same_cloud_twice_gives_the_same_text() -> None:
    # Given a 14,000-point cloud and its summary
    points = a_noisy_box()
    summary = a_summary_of(points)

    # When it is encoded twice
    first, second = encode_obj_text(summary, points), encode_obj_text(summary, points)

    # Then the tool result is reproducible
    assert first == second


def test_the_header_names_the_object_frame_up_axis_and_unit() -> None:
    # Given a car's cloud in the y-down demo map
    points = a_noisy_box()

    # When it is encoded
    text = encode_obj_text(a_summary_of(points, id="obj_17", label="car", up_axis="-y"), points)

    # Then the first line says what the block is and how to read it
    assert text.splitlines()[0] == "# surmap-obj v1 id=obj_17 label=car frame=map up=-y unit=cm"


def test_vertices_are_integer_centimetres_from_the_box_centre() -> None:
    # Given a 1 m square around (412.35, -88.10, 2.04)
    points = a_square()

    # When it is encoded
    text = encode_obj_text(a_summary_of(points), points)

    # Then each corner is written 50 cm from the centre, in input order
    assert v_lines(text) == ["v -50 0 -50", "v 50 0 -50", "v 50 0 50", "v -50 0 50"]


def test_a_small_cloud_keeps_every_point_and_is_not_marked_decimated() -> None:
    # Given four corners a metre apart, sparser than the 5 cm voxel
    points = a_square()

    # When it is encoded
    text = encode_obj_text(a_summary_of(points), points)

    # Then nothing was dropped and the header says so
    assert (len(v_lines(text)), "decimated" in text) == (4, False)


def test_a_decoded_block_returns_to_map_metres() -> None:
    # Given a 1 m square around (412.35, -88.10, 2.04)
    points = a_square()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points))

    # Then the corners are back where they were in the map
    assert np.allclose(decoded.points, points, atol=0.01)


def test_colours_ride_on_the_vertex_lines() -> None:
    # Given a coloured square
    points = a_square()

    # When it is encoded with its colours
    text = encode_obj_text(a_summary_of(points), points, colors=the_square_colours())

    # Then each vertex carries its r g b
    assert v_lines(text)[0] == "v -50 0 -50 158 156 153"


def test_colours_decode_back_unchanged() -> None:
    # Given a coloured square
    points, colours = a_square(), the_square_colours()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points, colors=colours))

    # Then the colours are the ones given
    assert decoded.colors is not None and decoded.colors.tolist() == colours.tolist()


def test_faces_encode_as_one_based_f_lines() -> None:
    # Given a square split into two triangles
    points, faces = a_square(), two_triangles()

    # When it is encoded with its faces
    text = encode_obj_text(a_summary_of(points), points, faces=faces)

    # Then the faces are OBJ's 1-based index lines
    assert f_lines(text) == ["f 1 2 3", "f 1 3 4"]


def test_faces_decode_back_to_zero_based_indices() -> None:
    # Given a square split into two triangles
    points, faces = a_square(), two_triangles()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points, faces=faces))

    # Then the same triangles come back
    assert decoded.faces is not None and decoded.faces.tolist() == faces.tolist()


def test_a_decoded_block_remembers_where_it_came_from() -> None:
    # Given a car's cloud in the y-down demo map
    points = a_noisy_box()

    # When it is encoded and read back
    decoded = decode_obj_text(encode_obj_text(a_summary_of(points), points))

    # Then the decoder knows the object, its frame and the original point count
    assert (decoded.id, decoded.label, decoded.frame, decoded.up_axis, decoded.decimated_from) == (
        "obj_17",
        "car",
        "map",
        "-y",
        14_000,
    )


def test_text_that_is_not_a_surmap_obj_block_is_refused() -> None:
    # Given a plain Wavefront OBJ file
    text = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"

    # When / Then decoding it is refused
    with pytest.raises(ValueError):
        decode_obj_text(text)


# --- GLB -------------------------------------------------------------------------------------


def test_a_glb_is_gltf_version_2() -> None:
    # Given a square's points
    points = a_square()

    # When they are written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="-y"))

    # Then the container is binary glTF 2.0
    assert (header.magic, header.version) == (b"glTF", 2)


def test_a_glb_header_states_the_file_length() -> None:
    # Given a square's points
    points = a_square()

    # When they are written as GLB
    data = write_glb(points, frame="map", up_axis="-y")

    # Then the header's length is the whole file
    assert read_glb_header(data).length == len(data)


def test_a_point_set_is_a_points_primitive() -> None:
    # Given a square's points and no faces
    points = a_square()

    # When they are written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="-y"))

    # Then the one primitive draws points (mode 0)
    assert header.primitive_modes == (0,)


def test_a_mesh_is_a_triangles_primitive() -> None:
    # Given a square split into two triangles
    points, faces = a_square(), two_triangles()

    # When it is written as GLB
    header = read_glb_header(write_glb(points, faces=faces, frame="map", up_axis="-y"))

    # Then the one primitive draws triangles (mode 4)
    assert header.primitive_modes == (4,)


def test_the_position_accessor_bounds_are_the_axis_aligned_box() -> None:
    # Given a 4 x 2 x 1 m box centred at (10, 5, 1)
    points = a_box(centre=(10.0, 5.0, 1.0))

    # When it is written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="+z"))

    # Then the accessor's min and max span the box
    assert spans(header.position_min, header.position_max, (8.0, 4.0, 0.5), (12.0, 6.0, 1.5))


def test_a_glb_names_its_frame_and_up_axis() -> None:
    # Given a square's points in the y-down demo map
    points = a_square()

    # When they are written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="-y"))

    # Then the asset says where its coordinates live
    assert header.asset_extras == {"frame": "map", "up_axis": "-y"}


def test_a_point_set_binary_chunk_holds_float32_positions() -> None:
    # Given four points
    points = a_square()

    # When they are written as GLB
    header = read_glb_header(write_glb(points, frame="map", up_axis="-y"))

    # Then the BIN chunk is four float32 xyz triples
    assert header.bin_chunk_length == 4 * 3 * 4
