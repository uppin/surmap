"""The SAM and object tools — `prompt_sam`, `find_objects`, `get_object`, `get_object_geometry`.

Integration tests over `DemoWorkspace` on recorded runs of the tiny EuRoC scene with objects of
known shape seeded into the run history, plus unit tests of the summary converter. Object
coordinates are in the run's map frame, up axis `-y`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.tools.handlers import (
    MAX_SAM_FRAMES,
    find_objects,
    get_object,
    get_object_geometry,
    object_summary_message,
    prompt_sam,
)
from surmap.objects3d import (
    Neighbour,
    Relation,
    decode_obj_text,
    read_glb_header,
)
from tests.agent_tool_fakes import (
    TINY_FULL_SIZE,
    ToolRig,
    a_cube,
    a_recorded_run,
    a_run_of_a_retired_scene,
    a_tool_rig,
    centred_box,
    with_an_object,
)
from tests.object_fakes import a_box, a_square, a_summary_of, is_within

BIG_BOX = "obj_1"  # 2 x 1 x 1 m box at (2, 0, 5): 2,541 points
SMALL_BOX = "obj_2"  # 0.6 m cube at (8, 0, 5): 343 points
WALKER = "obj_3"  # a moving 0.6 x 1.8 x 0.6 m person at (2, 0, 9)


def a_run_with_three_objects(rig: ToolRig) -> str:
    """A recorded run of the tiny scene with two static boxes and one moving person, seen on
    frame 1."""
    run_id = a_recorded_run(rig)
    with_an_object(rig, run_id, 1, a_box(centre=(2.0, 0.0, 5.0), half=(1.0, 0.5, 0.5)))
    with_an_object(rig, run_id, 2, a_cube(centre=(8.0, 0.0, 5.0), half=0.3), track_id=2)
    with_an_object(
        rig,
        run_id,
        3,
        a_box(centre=(2.0, 0.0, 9.0), half=(0.3, 0.9, 0.3)),
        label="person",
        track_id=3,
        moving=True,
    )
    return run_id


def frame_ids_of(response: pb.PromptSamResponse) -> list[int]:
    return [frame.frame_id for frame in response.frames]


def ids_of(response: pb.FindObjectsResponse) -> list[str]:
    return [found.id for found in response.objects]


def xyz(vector: pb.Vec3) -> tuple[float, float, float]:
    return (vector.x, vector.y, vector.z)


def box_of(box: pb.PixelBox) -> tuple[float, float, float, float]:
    return (box.x0, box.y0, box.x1, box.y1)


def is_box_near(
    actual: tuple[float, float, float, float],
    expected: tuple[float, float, float, float],
    px: float = 0.5,
) -> bool:
    return all(abs(a - e) <= px for a, e in zip(actual, expected, strict=True))


# --- prompt_sam -----------------------------------------------------------------------------


async def test_prompt_sam_segments_the_concept_on_the_chosen_frame(tmp_path: Path) -> None:
    # Given a recorded run of the tiny scene, cached at full resolution
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent looks for doors on its second frame
        response = await prompt_sam(
            pb.PromptSamRequest(run_id=run_id, concept="door", frame_ids=[2]), rig.workspace
        )

    # Then that frame alone answers, at its timestamp, with the fake SAM's door
    assert [(frame.frame_id, frame.t_ns) for frame in response.frames] == [(2, 200)]
    [door] = response.frames[0].detections
    assert (door.label, door.score) == ("door", 1.0)


async def test_prompt_sam_boxes_are_in_the_full_resolution_frame_s_pixels(tmp_path: Path) -> None:
    # Given a recorded run of the tiny scene, cached at full resolution
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent looks for doors on its first frame
        response = await prompt_sam(
            pb.PromptSamRequest(run_id=run_id, concept="door", frame_ids=[1]), rig.workspace
        )

    # Then the door's box is the fake SAM's centred box on the 752 x 480 frame, mask included
    [door] = response.frames[0].detections
    assert is_box_near(box_of(door.box_xyxy), centred_box(TINY_FULL_SIZE))
    assert len(door.mask_polygon) == 4


async def test_prompt_sam_picks_eight_evenly_spaced_frames_when_none_are_chosen(
    tmp_path: Path,
) -> None:
    # Given a recorded run of twenty frames
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_of_a_retired_scene(rig, frames=20)

        # When the agent prompts SAM without choosing frames
        response = await prompt_sam(
            pb.PromptSamRequest(run_id=run_id, concept="door"), rig.workspace
        )

    # Then eight frames are segmented, from the first to the last, in order
    picked = frame_ids_of(response)
    assert len(picked) == MAX_SAM_FRAMES == 8
    assert (picked[0], picked[-1]) == (1, 20)
    assert picked == sorted(set(picked))


async def test_prompt_sam_segments_at_most_max_frames(tmp_path: Path) -> None:
    # Given a recorded run of twenty frames
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_of_a_retired_scene(rig, frames=20)

        # When the agent asks for three frames
        response = await prompt_sam(
            pb.PromptSamRequest(run_id=run_id, concept="door", max_frames=3), rig.workspace
        )

    # Then three are segmented, spanning the run from its first frame to its last
    picked = frame_ids_of(response)
    assert (len(picked), picked[0], picked[-1]) == (3, 1, 20)


async def test_prompt_sam_never_segments_more_than_eight_frames(tmp_path: Path) -> None:
    # Given a recorded run of twenty frames
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_of_a_retired_scene(rig, frames=20)

        # When the agent asks for all twenty
        response = await prompt_sam(
            pb.PromptSamRequest(run_id=run_id, concept="door", max_frames=20), rig.workspace
        )

    # Then only eight are segmented
    assert len(response.frames) == MAX_SAM_FRAMES


async def test_prompt_sam_gives_every_detection_its_own_id(tmp_path: Path) -> None:
    # Given a recorded run of the tiny scene
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent prompts SAM on both of its frames
        response = await prompt_sam(
            pb.PromptSamRequest(run_id=run_id, concept="door", frame_ids=[1, 2]), rig.workspace
        )

    # Then no two detections share an id
    detection_ids = [d.detection_id for frame in response.frames for d in frame.detections]
    assert len(detection_ids) == 2 and len(set(detection_ids)) == 2 and all(detection_ids)


async def test_prompt_sam_refuses_a_frame_the_run_did_not_record(tmp_path: Path) -> None:
    # Given a recorded run of the tiny scene's two frames
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent prompts SAM on frame 99
        with pytest.raises(ConnectError) as refused:
            await prompt_sam(
                pb.PromptSamRequest(run_id=run_id, concept="door", frame_ids=[99]), rig.workspace
            )

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


async def test_prompt_sam_refuses_a_run_the_history_does_not_have(tmp_path: Path) -> None:
    # Given an empty history
    with a_tool_rig(tmp_path) as rig:
        # When the agent prompts SAM on a run
        with pytest.raises(ConnectError) as refused:
            await prompt_sam(
                pb.PromptSamRequest(run_id="no-such-run", concept="door"), rig.workspace
            )

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


# --- find_objects ---------------------------------------------------------------------------


async def test_find_objects_by_label_returns_those_objects_largest_first(tmp_path: Path) -> None:
    # Given a run with two boxes and a person
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent looks for boxes
        response = await find_objects(
            pb.FindObjectsRequest(run_id=run_id, label="box"), rig.workspace
        )

    # Then both boxes come back, the bigger one first
    assert ids_of(response) == [BIG_BOX, SMALL_BOX]


async def test_find_objects_near_a_point_keeps_only_objects_within_the_radius(
    tmp_path: Path,
) -> None:
    # Given a run with two boxes and a person
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent looks within a metre of the small box's centre
        response = await find_objects(
            pb.FindObjectsRequest(run_id=run_id, near=pb.Vec3(x=8.0, y=0.0, z=5.0), radius_m=1.0),
            rig.workspace,
        )

    # Then only the small box is that close
    assert ids_of(response) == [SMALL_BOX]


async def test_find_objects_near_a_point_lists_the_nearest_first(tmp_path: Path) -> None:
    # Given a run with two boxes and a person
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent looks within 10 m of a point just past the small box
        response = await find_objects(
            pb.FindObjectsRequest(run_id=run_id, near=pb.Vec3(x=9.0, y=0.0, z=5.0), radius_m=10.0),
            rig.workspace,
        )

    # Then the small box comes first, then the big box, then the person
    assert ids_of(response) == [SMALL_BOX, BIG_BOX, WALKER]


async def test_find_objects_can_keep_only_the_moving_ones(tmp_path: Path) -> None:
    # Given a run with two static boxes and a moving person
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks for moving objects
        response = await find_objects(
            pb.FindObjectsRequest(run_id=run_id, moving=True), rig.workspace
        )

    # Then only the person comes back, marked moving
    assert [(found.id, found.moving) for found in response.objects] == [(WALKER, True)]


async def test_find_objects_returns_at_most_limit_objects(tmp_path: Path) -> None:
    # Given a run with three objects
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks for one
        response = await find_objects(pb.FindObjectsRequest(run_id=run_id, limit=1), rig.workspace)

    # Then the largest alone comes back
    assert ids_of(response) == [BIG_BOX]


async def test_find_objects_refuses_near_without_a_radius(tmp_path: Path) -> None:
    # Given a run with objects
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent gives a point but no radius
        with pytest.raises(ConnectError) as refused:
            await find_objects(
                pb.FindObjectsRequest(run_id=run_id, near=pb.Vec3(x=8.0)), rig.workspace
            )

    # Then the request is invalid
    assert refused.value.code == Code.INVALID_ARGUMENT


async def test_find_objects_refuses_a_run_the_history_does_not_have(tmp_path: Path) -> None:
    # Given an empty history
    with a_tool_rig(tmp_path) as rig:
        # When the agent searches a run
        with pytest.raises(ConnectError) as refused:
            await find_objects(pb.FindObjectsRequest(run_id="no-such-run"), rig.workspace)

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


# --- get_object -----------------------------------------------------------------------------


async def test_get_object_summarises_the_object_s_extent_in_the_map_frame(tmp_path: Path) -> None:
    # Given a run with a 2 x 1 x 1 m box at (2, 0, 5)
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks about the box
        response = await get_object(
            pb.GetObjectRequest(run_id=run_id, object_id=BIG_BOX), rig.workspace
        )

    # Then its summary is the box, in metres of the -y-up map frame
    found = response.object
    assert (found.label, found.frame, found.up_axis, found.units) == ("box", "map", "-y", "m")
    assert is_within(xyz(found.centroid), (2.0, 0.0, 5.0), metres=0.01)
    assert is_within(xyz(found.aabb_min), (1.0, -0.5, 4.5), metres=0.01)
    assert is_within(xyz(found.aabb_max), (3.0, 0.5, 5.5), metres=0.01)
    assert (found.n_points, found.shape) == (2541, pb.VOLUMETRIC)


async def test_get_object_says_when_the_object_was_seen(tmp_path: Path) -> None:
    # Given a run whose box was seen on frame 1 only (t_ns 100)
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks about the box
        response = await get_object(
            pb.GetObjectRequest(run_id=run_id, object_id=BIG_BOX), rig.workspace
        )

    # Then it was observed once, at that frame's time
    found = response.object
    assert (found.observed_frames, found.t_first_ns, found.t_last_ns) == (1, 100, 100)


async def test_get_object_lists_its_neighbours_nearest_first(tmp_path: Path) -> None:
    # Given a run whose big box has the person 3.2 m beyond it and the small box 4.7 m beside it
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks about the big box
        response = await get_object(
            pb.GetObjectRequest(run_id=run_id, object_id=BIG_BOX), rig.workspace
        )

    # Then both are its neighbours, nearest first, at those distances
    assert [(n.id, round(n.distance_m, 1)) for n in response.object.neighbours] == [
        (WALKER, 3.2),
        (SMALL_BOX, 4.7),
    ]


async def test_get_object_names_where_its_geometry_lives(tmp_path: Path) -> None:
    # Given a run with a box
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks about the box
        response = await get_object(
            pb.GetObjectRequest(run_id=run_id, object_id=BIG_BOX), rig.workspace
        )

        # Then its geometry URI resolves to a GLB
        glb = rig.workspace.geometry.read(response.object.geometry_uri)
    assert glb is not None and read_glb_header(glb).magic == b"glTF"


async def test_get_object_refuses_an_object_the_run_does_not_have(tmp_path: Path) -> None:
    # Given a run with three objects
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks about obj_99
        with pytest.raises(ConnectError) as refused:
            await get_object(pb.GetObjectRequest(run_id=run_id, object_id="obj_99"), rig.workspace)

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


# --- get_object_geometry --------------------------------------------------------------------


async def test_get_object_geometry_returns_obj_text_within_max_points(tmp_path: Path) -> None:
    # Given a run with a 2,541-point box
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks for at most 100 of its points
        response = await get_object_geometry(
            pb.GetObjectGeometryRequest(run_id=run_id, object_id=BIG_BOX, max_points=100),
            rig.workspace,
        )

    # Then the text is a surmap-obj block of that box, thinned to fit, saying from how many
    decoded = decode_obj_text(response.obj_text)
    assert (decoded.id, decoded.frame, decoded.up_axis) == (BIG_BOX, "map", "-y")
    assert len(decoded.points) <= 100
    assert response.decimated_from == 2541


async def test_get_object_geometry_keeps_the_default_limit_of_500_points(tmp_path: Path) -> None:
    # Given a run with a 2,541-point box
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks for its geometry with no limits
        response = await get_object_geometry(
            pb.GetObjectGeometryRequest(run_id=run_id, object_id=BIG_BOX), rig.workspace
        )

    # Then at most 500 points come back
    assert 0 < len(decode_obj_text(response.obj_text).points) <= 500


async def test_get_object_geometry_s_glb_spans_the_object(tmp_path: Path) -> None:
    # Given a run with a box spanning (1, -0.5, 4.5) to (3, 0.5, 5.5)
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks for its geometry
        response = await get_object_geometry(
            pb.GetObjectGeometryRequest(run_id=run_id, object_id=BIG_BOX), rig.workspace
        )

        # Then the GLB its URI names holds the whole box
        glb = rig.workspace.geometry.read(response.geometry_uri)
    assert glb is not None
    header = read_glb_header(glb)
    assert is_within(header.position_min, (1.0, -0.5, 4.5), metres=0.01)
    assert is_within(header.position_max, (3.0, 0.5, 5.5), metres=0.01)


async def test_get_object_geometry_refuses_an_object_the_run_does_not_have(
    tmp_path: Path,
) -> None:
    # Given a run with three objects
    with a_tool_rig(tmp_path) as rig:
        run_id = a_run_with_three_objects(rig)

        # When the agent asks for obj_99's geometry
        with pytest.raises(ConnectError) as refused:
            await get_object_geometry(
                pb.GetObjectGeometryRequest(run_id=run_id, object_id="obj_99"), rig.workspace
            )

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


# --- object_summary_message -----------------------------------------------------------------


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
