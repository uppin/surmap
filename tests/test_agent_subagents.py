"""Starting a subagent: its own session, runner and history on the task it was given, its turn an
ASYNC job of the main conversation whose result is its final answer; and cancelling that job.

The main and the subagent models are scripted separately; held handlers are released by events,
never by sleeps.
"""

from __future__ import annotations

import asyncio

from langchain_core.messages import (
    SystemMessage,
    ToolMessage,
)

from surmap.agent.runtime.jobs import JobNotice, JobState
from tests.agent_fakes import (
    FakeToolHandler,
    ScriptedChatModel,
    answer,
    calling,
    collect,
    human_texts,
    tool_call,
    tool_message_for,
)
from tests.agent_server_fakes import (
    STEP_TIMEOUT_S,
)
from tests.agent_subagent_fakes import (
    SKILL_BODY,
    SUBAGENT_PROMPT,
    TASK,
    a_main_agent_with_subagents,
    result_of,
    starting_the_scene_builder,
)

# --- starting a subagent -------------------------------------------------------------------


async def test_start_subagent_reports_the_subagent_and_the_job_its_turn_runs_as() -> None:
    # Given a main agent that starts the scene builder
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started.")),
        ScriptedChatModel.replying(answer("Scene wildfire-1 built.")),
    )

    # When its turn runs
    await collect(rig.main.run_turn("Make me a wildfire scene"))

    # Then the call names subagent sa-1 and the job j-2 its turn runs as
    assert result_of(rig.main_history, "s1") == {
        "subagent_id": "sa-1",
        "name": "scene-builder",
        "job_id": "j-2",
    }


async def test_the_subagent_reads_the_task_as_its_first_message() -> None:
    # Given a main agent that starts the scene builder
    subagent = ScriptedChatModel.replying(answer("Scene wildfire-1 built."))
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started.")), subagent
    )

    # When its turn runs and the subagent's turn ends
    await collect(rig.main.run_turn("Make me a wildfire scene"))
    await rig.subagent_job("j-2")

    # Then the subagent was asked exactly the task
    assert human_texts(subagent.history_of_call(1)) == [TASK]


async def test_the_subagent_s_instructions_are_the_subagent_prompt_and_its_skill() -> None:
    # Given a main agent that starts the scene builder with the simulation skill
    subagent = ScriptedChatModel.replying(answer("Scene wildfire-1 built."))
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started.")), subagent
    )

    # When the subagent runs
    await collect(rig.main.run_turn("Make me a wildfire scene"))
    await rig.subagent_job("j-2")

    # Then its system message carries the subagent prompt and the skill's body
    system = subagent.history_of_call(1)[0]
    assert isinstance(system, SystemMessage)
    assert SUBAGENT_PROMPT in system.text
    assert SKILL_BODY in system.text


async def test_the_subagent_s_final_answer_is_its_job_s_result() -> None:
    # Given a scene builder that adds a fire and reports
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started.")),
        ScriptedChatModel.replying(
            calling(tool_call("add_fire", "c1", scenario_id="wildfire-1")),
            answer("Scene wildfire-1 built."),
        ),
    )

    # When the subagent's turn ends
    await collect(rig.main.run_turn("Make me a wildfire scene"))
    job = await rig.subagent_job("j-2")

    # Then its job succeeded with the reply
    assert job.tool == "subagent:sa-1"
    assert job.state is JobState.SUCCEEDED
    assert job.result == {
        "subagent_id": "sa-1",
        "name": "scene-builder",
        "finish_reason": "stop",
        "reply": "Scene wildfire-1 built.",
    }


async def test_the_subagent_s_tool_calls_stay_out_of_the_main_conversation() -> None:
    # Given a scene builder that adds a fire
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started.")),
        ScriptedChatModel.replying(
            calling(tool_call("add_fire", "c1", scenario_id="wildfire-1")),
            answer("Scene wildfire-1 built."),
        ),
    )

    # When it has built the scene
    await collect(rig.main.run_turn("Make me a wildfire scene"))
    await rig.subagent_job("j-2")

    # Then the fire was added, and the main conversation holds no add_fire call
    assert rig.add_fire.calls == [{"scenario_id": "wildfire-1"}]
    assert [m.name for m in rig.main_history if isinstance(m, ToolMessage)] == ["start_subagent"]


async def test_a_subagent_that_ends_while_the_main_agent_idles_reports_as_a_job_notice() -> None:
    # Given a scene builder started by a turn that has ended
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started.")),
        ScriptedChatModel.replying(answer("Scene wildfire-1 built.")),
    )
    await collect(rig.main.run_turn("Make me a wildfire scene"))

    # When the subagent ends
    await rig.subagent_job("j-2")
    notice = await asyncio.wait_for(anext(rig.main.idle_events()), STEP_TIMEOUT_S)

    # Then the main agent is told the subagent's job succeeded, with its reply
    assert isinstance(notice, JobNotice)
    assert notice.job.job_id == "j-2"
    assert "Scene wildfire-1 built." in notice.text


async def test_the_subagent_is_offered_its_tools_and_message_main_agent_but_no_subagent_tools() -> (
    None
):
    # Given a main agent that starts the scene builder
    subagent = ScriptedChatModel.replying(answer("Scene wildfire-1 built."))
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started.")), subagent
    )

    # When the subagent runs
    await collect(rig.main.run_turn("Make me a wildfire scene"))
    await rig.subagent_job("j-2")

    # Then it may add fires and message the main agent, but not start or message subagents
    offered = subagent.bound_tool_names[0]
    assert {"add_fire", "wait_for_jobs", "message_main_agent"} <= set(offered)
    assert not {"start_subagent", "message_subagent"} & set(offered)


async def test_start_subagent_with_an_unknown_skill_fails_and_starts_nothing() -> None:
    # Given a main agent that names a skill nobody wrote
    subagent = ScriptedChatModel.replying(answer("Never said."))
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(
            calling(tool_call("start_subagent", "s1", task=TASK, skill="no-such-skill")),
            answer("It failed."),
        ),
        subagent,
    )

    # When its turn runs
    await collect(rig.main.run_turn("Make me a wildfire scene"))

    # Then the call failed naming the skill, and no subagent model ran
    failed = tool_message_for(rig.main_history, "s1")
    assert failed.status == "error"
    assert "no-such-skill" in str(failed.content)
    assert subagent.calls == 0


async def test_start_subagent_is_refused_past_the_running_cap() -> None:
    # Given a cap of one running subagent, and a first one holding on its fire
    fire = FakeToolHandler.holding({"fire_id": "fire-1"})
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(
            starting_the_scene_builder("s1"), starting_the_scene_builder("s2"), answer("One.")
        ),
        ScriptedChatModel.replying(
            calling(tool_call("add_fire", "c1", scenario_id="wildfire-1")), answer("Built.")
        ),
        add_fire=fire,
        max_running=1,
    )

    # When the main agent starts a second while the first still runs
    await collect(rig.main.run_turn("Make me two scenes"))

    # Then the second start fails naming the cap
    refused = tool_message_for(rig.main_history, "s2")
    assert refused.status == "error"
    assert "at most 1" in str(refused.content)
    fire.release()
    await rig.subagent_job("j-2")


async def test_cancelling_the_subagent_s_job_cancels_its_turn_and_its_tool_calls() -> None:
    # Given a scene builder holding on a fire edit
    fire = FakeToolHandler.holding({"fire_id": "fire-1"})
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started.")),
        ScriptedChatModel.replying(
            calling(tool_call("add_fire", "c1", scenario_id="wildfire-1")), answer("Never said.")
        ),
        add_fire=fire,
    )
    await collect(rig.main.run_turn("Make me a wildfire scene"))
    await asyncio.wait_for(fire.started.wait(), STEP_TIMEOUT_S)

    # When the main agent cancels the subagent's job
    rig.main_runner.cancel("j-2")
    job = await rig.subagent_job("j-2")

    # Then the job is cancelled and so is the fire edit it was waiting on
    assert job.state is JobState.CANCELLED
    assert fire.was_cancelled
