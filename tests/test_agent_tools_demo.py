"""The demo tools — `list_demos`, `run_demo`, `get_run` — on a headless demo run host.

Integration tests over `DemoWorkspace`: the tiny two-frame EuRoC scene, no RTAB-Map, the fake
centred-box SAM, a temp scene cache and history DB.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.services import survey_tools_module
from surmap.agent.tools.handlers import get_run, list_demos, run_demo, survey_tool_handlers
from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.in_memory import InMemoryHost
from tests.agent_tool_fakes import (
    TINY_SCENE,
    a_recorded_run,
    a_tool_rig,
    eventually,
    settled,
    the_run_started_by,
    the_run_started_by_the_host,
)

SURVEY_TOOLS = pb.DESCRIPTOR.services_by_name["SurveyTools"]


def a_tiny_run(**fields: object) -> pb.RunDemoRequest:
    """A fast run of the tiny scene; `fields` override the request."""
    request = pb.RunDemoRequest(dataset=TINY_SCENE, fps=50.0)
    for name, value in fields.items():
        setattr(request, name, value)
    return request


def prompts_by_scene(response: pb.ListDemosResponse) -> dict[str, str]:
    return {scene.id: scene.default_prompt for scene in response.scenes}


def scene_in(response: pb.ListDemosResponse, scene_id: str) -> pb.DemoScene:
    return next(scene for scene in response.scenes if scene.id == scene_id)


# --- list_demos -----------------------------------------------------------------------------


async def test_list_demos_offers_every_scene_with_its_default_sam_prompt(tmp_path: Path) -> None:
    # Given a workspace over the registry's scenes plus the tiny fixture scene
    with a_tool_rig(tmp_path) as rig:
        # When the agent lists the demos
        response = await list_demos(pb.ListDemosRequest(), rig.workspace)

    # Then every scene is offered with the concept SAM looks for by default
    assert prompts_by_scene(response) == {
        TINY_SCENE: "object",
        "euroc-v1-01-easy": "box",
        "kitti-2011-09-26-drive-0009": "car",
        "ntu-viral-sbs-01": "person",
    }


async def test_list_demos_says_only_the_cached_scene_is_prepared(tmp_path: Path) -> None:
    # Given a scene cache holding only the tiny scene
    with a_tool_rig(tmp_path) as rig:
        # When the agent lists the demos
        response = await list_demos(pb.ListDemosRequest(), rig.workspace)

    # Then the tiny scene is prepared and the registry scenes still need a download
    assert {scene.id: scene.prepared for scene in response.scenes} == {
        TINY_SCENE: True,
        "euroc-v1-01-easy": False,
        "kitti-2011-09-26-drive-0009": False,
        "ntu-viral-sbs-01": False,
    }


async def test_list_demos_names_a_scene_s_recorded_run_once_it_has_one(tmp_path: Path) -> None:
    # Given the tiny scene recorded once
    with a_tool_rig(tmp_path) as rig:
        run_id = a_recorded_run(rig)

        # When the agent lists the demos
        response = await list_demos(pb.ListDemosRequest(), rig.workspace)

    # Then that recording is the scene's cached run
    assert scene_in(response, TINY_SCENE).cached_run_id == run_id


async def test_list_demos_names_no_cached_run_for_a_scene_never_recorded(tmp_path: Path) -> None:
    # Given an empty history
    with a_tool_rig(tmp_path) as rig:
        # When the agent lists the demos
        response = await list_demos(pb.ListDemosRequest(), rig.workspace)

    # Then the tiny scene has no cached run
    assert not scene_in(response, TINY_SCENE).HasField("cached_run_id")


# --- run_demo -------------------------------------------------------------------------------


async def test_run_demo_plays_the_scene_to_its_end(tmp_path: Path) -> None:
    # Given a workspace over the tiny two-frame scene
    with a_tool_rig(tmp_path) as rig:
        # When the agent runs it looking for boxes
        response = await run_demo(a_tiny_run(prompt="box"), rig.workspace)

    # Then the run finished having recorded both frames
    assert (response.status, response.frames) == (pb.RunInfo.FINISHED, 2)


async def test_run_demo_records_an_ordinary_run_in_the_demo_history(tmp_path: Path) -> None:
    # Given a workspace over the tiny scene
    with a_tool_rig(tmp_path) as rig:
        # When the agent runs it
        response = await run_demo(a_tiny_run(prompt="box"), rig.workspace)

        # Then the console's history has the run, completed
        assert rig.history_status(response.run_id) == "completed"


async def test_run_demo_stops_after_max_frames(tmp_path: Path) -> None:
    # Given a workspace over the tiny two-frame scene
    with a_tool_rig(tmp_path) as rig:
        # When the agent runs only its first frame
        response = await run_demo(a_tiny_run(max_frames=1), rig.workspace)

    # Then the run recorded one frame
    assert response.frames == 1


async def test_run_demo_refuses_a_scene_the_station_does_not_offer(tmp_path: Path) -> None:
    # Given a workspace with no scene called "atlantis"
    with a_tool_rig(tmp_path) as rig:
        # When the agent runs it
        with pytest.raises(ConnectError) as refused:
            await run_demo(pb.RunDemoRequest(dataset="atlantis"), rig.workspace)

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


async def test_cancelling_run_demo_stops_the_run_it_started(tmp_path: Path) -> None:
    # Given a slow run of the tiny scene in progress, one frame every two seconds
    with a_tool_rig(tmp_path) as rig:
        call = asyncio.create_task(run_demo(a_tiny_run(fps=0.5), rig.workspace))
        run_id = await the_run_started_by(rig, call)

        # When the agent's call is cancelled
        call.cancel()
        await settled(call)

        # Then the run is stopped and its history says it was cut short
        await eventually(lambda: rig.history_status(run_id) == "interrupted")


async def test_cancelling_run_demo_while_its_run_is_starting_stops_that_run(
    tmp_path: Path,
) -> None:
    # Given a slow run whose start is held up behind the host's run lock
    with a_tool_rig(tmp_path) as rig:
        with rig.host.run_lock:
            call = asyncio.create_task(run_demo(a_tiny_run(fps=0.5), rig.workspace))
            await asyncio.sleep(0.3)

            # When the agent's call is cancelled before the run has started
            call.cancel()

        # Then the run that starts once the lock frees is stopped, and its history says so
        await settled(call)
        run_id = await the_run_started_by_the_host(rig)
        await eventually(lambda: rig.history_status(run_id) == "interrupted")


# --- get_run --------------------------------------------------------------------------------


async def test_get_run_describes_the_run_run_demo_played(tmp_path: Path) -> None:
    # Given a finished run of the tiny scene looking for boxes
    with a_tool_rig(tmp_path) as rig:
        played = await run_demo(a_tiny_run(prompt="box"), rig.workspace)

        # When the agent asks about it
        response = await get_run(pb.GetRunRequest(run_id=played.run_id), rig.workspace)

    # Then it is that run: its scene, prompt, frames, objects and status
    assert response.run == pb.RunInfo(
        run_id=played.run_id,
        dataset=TINY_SCENE,
        prompt="box",
        frames=2,
        objects=played.objects,
        status=pb.RunInfo.FINISHED,
    )


async def test_get_run_reports_the_scene_s_default_prompt_when_none_was_given(
    tmp_path: Path,
) -> None:
    # Given a finished run of the tiny scene started without a prompt
    with a_tool_rig(tmp_path) as rig:
        played = await run_demo(a_tiny_run(), rig.workspace)

        # When the agent asks about it
        response = await get_run(pb.GetRunRequest(run_id=played.run_id), rig.workspace)

    # Then SAM looked for the scene's default concept
    assert response.run.prompt == "object"


async def test_get_run_reports_a_run_cut_short_as_cancelled(tmp_path: Path) -> None:
    # Given a run the agent cancelled mid-way
    with a_tool_rig(tmp_path) as rig:
        call = asyncio.create_task(run_demo(a_tiny_run(fps=0.5), rig.workspace))
        run_id = await the_run_started_by(rig, call)
        call.cancel()
        await settled(call)
        await eventually(lambda: rig.history_status(run_id) == "interrupted")

        # When the agent asks about it
        response = await get_run(pb.GetRunRequest(run_id=run_id), rig.workspace)

    # Then it is cancelled
    assert response.run.status == pb.RunInfo.CANCELLED


async def test_get_run_refuses_a_run_the_history_does_not_have(tmp_path: Path) -> None:
    # Given an empty history
    with a_tool_rig(tmp_path) as rig:
        # When the agent asks about a run
        with pytest.raises(ConnectError) as refused:
            await get_run(pb.GetRunRequest(run_id="no-such-run"), rig.workspace)

    # Then the call fails as not found
    assert refused.value.code == Code.NOT_FOUND


# --- survey_tool_handlers -------------------------------------------------------------------


def test_survey_tool_handlers_serve_every_survey_tools_rpc(tmp_path: Path) -> None:
    # Given a workspace
    with a_tool_rig(tmp_path) as rig:
        # When its handlers are built
        handlers = survey_tool_handlers(rig.workspace)

    # Then there is one per SurveyTools rpc, by rpc name
    assert set(handlers) == {method.name for method in SURVEY_TOOLS.methods}


async def test_survey_tool_handlers_answer_through_the_survey_tools_service(
    tmp_path: Path,
) -> None:
    # Given the SurveyTools service mounted in memory on a workspace's handlers
    with a_tool_rig(tmp_path) as rig:
        module = survey_tools_module(survey_tool_handlers(rig.workspace))
        client = InMemoryHost(ServerDescription(services=(module,)), None).client(SURVEY_TOOLS)

        # When a client lists the demos over the service
        answer = await client.unary("ListDemos", pb.ListDemosRequest())

    # Then it gets the workspace's scenes
    assert TINY_SCENE in prompts_by_scene(
        pb.ListDemosResponse.FromString(answer.SerializeToString())
    )
