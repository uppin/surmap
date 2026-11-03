"""The summary converter — `object_summary_message`, from `surmap.objects3d` to the proto.

Unit tests on summaries of objects of known shape; coordinates are in the map frame, up `-y`.
"""

from __future__ import annotations

from dataclasses import replace

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.tools.handlers import object_summary_message
from surmap.objects3d import Neighbour, Relation
from tests.agent_tool_fakes import xyz
from tests.object_fakes import a_square, a_summary_of, is_within


def test_the_summary_s_oriented_box_becomes_an_oriented_box_with_a_flat_rotation() -> None:
    # Given a summary of a square whose box is axis-aligned
    summary = a_summary_of(a_square())

    # When it is converted to its proto
    message = object_summary_message(summary, moving=False)

    # Then the box centre and extents carry over and the rotation is nine row-major values
    assert is_within(xyz(message.obb.centre), summary.obb.centre, metres=1e-9)
    assert is_within(xyz(message.obb.extents), summary.obb.extents, metres=1e-9)
    assert list(message.obb.rotation) == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]


def test_the_summary_s_shape_class_becomes_the_proto_shape() -> None:
    # Given a summary of a volumetric object
    summary = a_summary_of(a_square())

    # When it is converted to its proto
    message = object_summary_message(summary, moving=False)

    # Then its shape is the proto's VOLUMETRIC
    assert message.shape == pb.VOLUMETRIC


def test_a_summary_s_missing_times_confidence_and_uri_become_zero_and_empty() -> None:
    # Given a summary with no confidence, no observation times and no published geometry
    summary = replace(a_summary_of(a_square()), confidence=None)

    # When it is converted to its proto
    message = object_summary_message(summary, moving=False)

    # Then those fields are proto3's zero values
    assert (message.confidence, message.t_first_ns, message.t_last_ns, message.geometry_uri) == (
        0.0,
        0,
        0,
        "",
    )


def test_the_summary_s_identity_counts_and_extent_carry_over() -> None:
    # Given a summary of obj_17, a car of four points in the -y-up map frame
    summary = a_summary_of(a_square())

    # When it is converted to its proto
    message = object_summary_message(summary, moving=False)

    # Then its identity, frame, counts and boxes are the summary's
    assert (message.id, message.label, message.frame, message.up_axis, message.units) == (
        "obj_17",
        "car",
        "map",
        "-y",
        "m",
    )
    assert (message.n_points, message.n_faces, message.observed_frames) == (4, 0, 1)
    assert (xyz(message.aabb_min), xyz(message.aabb_max)) == (summary.aabb_min, summary.aabb_max)


def test_the_summary_s_neighbours_keep_their_relation() -> None:
    # Given a summary with a neighbour above it and one beside it
    summary = replace(
        a_summary_of(a_square()),
        neighbours=(
            Neighbour("obj_2", 0.5, Relation.ABOVE),
            Neighbour("obj_3", 1.5, Relation.NEXT_TO),
        ),
    )

    # When it is converted to its proto
    message = object_summary_message(summary, moving=False)

    # Then each neighbour keeps its id, distance and relation, in order
    assert [(n.id, n.distance_m, n.relation) for n in message.neighbours] == [
        ("obj_2", 0.5, pb.ABOVE),
        ("obj_3", 1.5, pb.NEXT_TO),
    ]


def test_the_converted_summary_says_whether_the_object_moved() -> None:
    # Given a summary of an object that moved during the run
    summary = a_summary_of(a_square())

    # When it is converted to its proto as moving
    message = object_summary_message(summary, moving=True)

    # Then the proto says it moved
    assert message.moving is True
