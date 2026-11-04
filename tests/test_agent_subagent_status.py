"""A subagent's status for the tasks panel: running as its turn's job once started, the text it
reports with `report_status` while it works, and how its turn ended. Neither model reads it; the
hub records it and hands it to the conversation's watchers without opening a turn.

The main and the subagent models are scripted separately; held handlers are released by events,
never by sleeps.
"""

from __future__ import annotations

import asyncio

from surmap.agent.proto import chat_pb2, execution_pb2
from surmap.agent.runtime.events import SubagentStatus
from surmap.agent.runtime.jobs import JobNotice, JobState
from surmap.agent.server.app import SUBAGENT_PROMPT as SHIPPED_SUBAGENT_PROMPT
from surmap.agent.subagents import SubagentSetup
from tests.agent_fakes import (
    FakeToolHandler,
    ScriptedChatModel,
    answer,
    calling,
    collect,
    tool_call,
)
from tests.agent_server_fakes import (
    CONVERSATION,
    STEP_TIMEOUT_S,
    TurnStream,
    a_chat_rig,
    a_turn,
    eventually,
)
from tests.agent_subagent_fakes import (
    SKILL_BODY,
    SUBAGENT_PROMPT,
    TwoAgentChatModel,
    a_main_agent_with_subagents,
    a_skill_loader,
    starting_the_scene_builder,
)

PLACING = "Placing the house"


def a_main_agent_that_starts_the_scene_builder() -> ScriptedChatModel:
    return ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started."))


def a_scene_builder_that_reports(status: str = PLACING) -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(tool_call("report_status", "r1", status=status)), answer("Scene house-1 built.")
    )


def the_scene_builder(state: JobState, *, job_id: str = "j-2", detail: str = "") -> SubagentStatus:
    return SubagentStatus(
        subagent_id="sa-1", name="scene-builder", job_id=job_id, state=state, detail=detail
    )


# --- what the pool reports -----------------------------------------------------------------


async def test_a_started_subagent_is_reported_running_as_its_turn_s_job() -> None:
    # Given a main agent that starts the scene builder
    rig = a_main_agent_with_subagents(
        a_main_agent_that_starts_the_scene_builder(),
        ScriptedChatModel.replying(answer("Scene house-1 built.")),
    )

    # When its turn runs
    await collect(rig.main.run_turn("A tree and a house"))

    # Then the first status is the scene builder running as job j-2, with nothing reported yet
    assert rig.statuses[0] == the_scene_builder(JobState.RUNNING)


async def test_report_status_shows_what_the_subagent_says_it_is_doing() -> None:
    # Given a scene builder that reports what it is doing
    rig = a_main_agent_with_subagents(
        a_main_agent_that_starts_the_scene_builder(), a_scene_builder_that_reports()
    )

    # When it runs
    await collect(rig.main.run_turn("A tree and a house"))
    await rig.subagent_job("j-2")

    # Then its status carries the text it reported
    assert the_scene_builder(JobState.RUNNING, detail=PLACING) in rig.statuses


async def test_the_main_agent_never_reads_a_reported_status() -> None:
    # Given a scene builder that reports what it is doing
    rig = a_main_agent_with_subagents(
        a_main_agent_that_starts_the_scene_builder(), a_scene_builder_that_reports()
    )

    # When it runs to the end
    await collect(rig.main.run_turn("A tree and a house"))
    await rig.subagent_job("j-2")

    # Then the main agent is notified only of the finished job, which says nothing of the status
    notice = rig.main_runner.notices.get_nowait()
    assert isinstance(notice, JobNotice)
    assert PLACING not in notice.text
    assert rig.main_runner.notices.empty()


async def test_a_finished_subagent_is_reported_succeeded_keeping_its_last_status() -> None:
    # Given a scene builder that reports what it is doing
    rig = a_main_agent_with_subagents(
        a_main_agent_that_starts_the_scene_builder(), a_scene_builder_that_reports()
    )

    # When it runs to the end
    await collect(rig.main.run_turn("A tree and a house"))
    await rig.subagent_job("j-2")

    # Then its last status is succeeded, still saying what it last reported
    assert rig.statuses[-1] == the_scene_builder(JobState.SUCCEEDED, detail=PLACING)


async def test_a_cancelled_subagent_is_reported_cancelled() -> None:
    # Given a scene builder holding on a fire edit
    fire = FakeToolHandler.holding({"fire_id": "fire-1"})
    rig = a_main_agent_with_subagents(
        a_main_agent_that_starts_the_scene_builder(),
        ScriptedChatModel.replying(
            calling(tool_call("add_fire", "c1", scenario_id="house-1")), answer("Never said.")
        ),
        add_fire=fire,
    )
    await collect(rig.main.run_turn("A tree and a house"))
    await asyncio.wait_for(fire.started.wait(), STEP_TIMEOUT_S)

    # When its job is cancelled
    rig.main_runner.cancel("j-2")
    await rig.subagent_job("j-2")

    # Then its last status is cancelled
    assert rig.statuses[-1] == the_scene_builder(JobState.CANCELLED)


async def test_a_follow_up_turn_is_reported_running_as_its_new_job() -> None:
    # Given a scene builder whose first turn has ended
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(
            starting_the_scene_builder(),
            answer("Started."),
            calling(tool_call("message_subagent", "m1", subagent_id="sa-1", text="Add a tree")),
            answer("Asked for a tree."),
        ),
        ScriptedChatModel.replying(answer("Scene house-1 built.")),
    )
    await collect(rig.main.run_turn("A house"))
    await rig.subagent_job("j-2")

    # When the main agent messages it, starting its follow-up turn as job j-4
    await collect(rig.main.run_turn("Add a tree"))
    await rig.subagent_job("j-4")

    # Then the scene builder is reported running as j-4
    assert the_scene_builder(JobState.RUNNING, job_id="j-4") in rig.statuses


async def test_the_subagent_is_offered_report_status() -> None:
    # Given a main agent that starts the scene builder
    subagent = ScriptedChatModel.replying(answer("Scene house-1 built."))
    rig = a_main_agent_with_subagents(a_main_agent_that_starts_the_scene_builder(), subagent)

    # When the subagent runs
    await collect(rig.main.run_turn("A tree and a house"))
    await rig.subagent_job("j-2")

    # Then report_status is among its tools
    assert "report_status" in subagent.bound_tool_names[0]


def test_the_shipped_subagent_prompt_tells_it_to_report_its_status_with_report_status() -> None:
    # Given the prompt every shipped subagent starts from
    prompt = SHIPPED_SUBAGENT_PROMPT

    # Then it names the tool to report status with
    assert "report_status" in prompt


# --- what the hub delivers -----------------------------------------------------------------


async def test_a_subagent_s_status_reaches_the_watchers_before_the_turn_its_end_opens() -> None:
    # Given a scene builder holding on a demo, started by a main turn that has ended
    demo = FakeToolHandler.holding({"run_id": "run-1"})
    subagent = ScriptedChatModel.replying(
        calling(tool_call("run_demo", "d1", dataset="euroc-v1-01-easy")),
        calling(tool_call("report_status", "r1", status=PLACING)),
        answer("Scene house-1 built."),
    )
    model = TwoAgentChatModel(
        script=a_main_agent_that_starts_the_scene_builder().script, subagent=subagent
    )
    setup = SubagentSetup(
        system_prompt=SUBAGENT_PROMPT,
        load_skill=a_skill_loader({"building-a-simulation-scene": SKILL_BODY}),
    )
    async with a_chat_rig(model, subagents=setup, run_demo=demo) as rig:
        await a_turn(rig, "A tree and a house")
        watch = TurnStream.watching(rig)
        await eventually(lambda: rig.hub.watchers(CONVERSATION) == 1)
        await asyncio.wait_for(demo.started.wait(), STEP_TIMEOUT_S)

        # When the demo ends and the scene builder reports, then finishes
        demo.release()
        await watch.turn()

    # Then its statuses arrive outside any turn, before the job update that opens one
    first_three = [event.WhichOneof("event") for event in watch.events[:3]]
    assert first_three == ["subagent_status", "subagent_status", "job_update"]
    reported, finished = watch.events[0], watch.events[1]
    assert reported.turn_id == ""
    assert reported.subagent_status == chat_pb2.SubagentStatus(
        subagent_id="sa-1",
        name="scene-builder",
        job_id="j-2",
        status=execution_pb2.RUNNING,
        detail=PLACING,
    )
    assert finished.subagent_status.status == execution_pb2.SUCCEEDED


async def test_a_subagent_s_status_is_kept_in_the_conversation_s_replay() -> None:
    # Given a scene builder that reports what it is doing, started by a main turn
    model = TwoAgentChatModel(
        script=a_main_agent_that_starts_the_scene_builder().script,
        subagent=a_scene_builder_that_reports(),
    )
    setup = SubagentSetup(
        system_prompt=SUBAGENT_PROMPT,
        load_skill=a_skill_loader({"building-a-simulation-scene": SKILL_BODY}),
    )
    async with a_chat_rig(model, subagents=setup) as rig:
        await a_turn(rig, "A tree and a house")
        runner = rig.hub.runner(CONVERSATION)
        assert runner is not None
        await runner.wait(["j-2"], "all", STEP_TIMEOUT_S)

        # When the conversation is read back
        replay = await rig.chat.unary(
            "GetConversation", chat_pb2.GetConversationRequest(conversation_id=CONVERSATION)
        )

    # Then the status the scene builder reported is in it
    assert isinstance(replay, chat_pb2.GetConversationResponse)
    details = [e.subagent_status.detail for e in replay.events if e.HasField("subagent_status")]
    assert PLACING in details
