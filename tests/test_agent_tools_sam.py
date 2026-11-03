"""The SAM tool — `prompt_sam` on a recorded run's frames.

Integration tests over `DemoWorkspace` on recorded runs of the tiny EuRoC scene, with the fake
SAM detector that boxes the frame's centre.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.tools.handlers import MAX_SAM_FRAMES, prompt_sam
from tests.agent_tool_fakes import (
    TINY_FULL_SIZE,
    a_recorded_run,
    a_run_of_a_retired_scene,
    a_tool_rig,
    centred_box,
)


def frame_ids_of(response: pb.PromptSamResponse) -> list[int]:
    return [frame.frame_id for frame in response.frames]


def box_of(box: pb.PixelBox) -> tuple[float, float, float, float]:
    return (box.x0, box.y0, box.x1, box.y1)


def is_box_near(
    actual: tuple[float, float, float, float],
    expected: tuple[float, float, float, float],
    px: float = 0.5,
) -> bool:
    return all(abs(a - e) <= px for a, e in zip(actual, expected, strict=True))


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
