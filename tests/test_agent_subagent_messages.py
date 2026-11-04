"""Messages between the main agent and its subagent: `message_main_agent` reaches the main agent
as a tagged notice (mid-turn, or opening a turn while it idles), and `message_subagent` steers a
running subagent or starts its follow-up turn on the history it kept."""

from __future__ import annotations

import asyncio

from surmap.agent.proto import chat_pb2
from surmap.agent.runtime.events import SubagentMessage
from surmap.agent.runtime.jobs import JobState, SubagentNotice
from surmap.agent.subagents import SUBAGENT_KIND
from tests.agent_fakes import (
    FakeToolHandler,
    ScriptedChatModel,
    answer,
    calling,
    collect,
    human_texts,
    tool_call,
    tool_message_for,
    until_held,
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
    QUESTION,
    TASK,
    a_main_agent_with_subagents,
    a_scene_builder_that_asks,
    result_of,
    starting_the_scene_builder,
    tagged,
)

# --- the subagent messages the main agent --------------------------------------------------


async def test_a_subagent_message_during_a_main_turn_is_read_before_the_next_model_call() -> None:
    # Given a main turn that started the scene builder and then blocks on its own fire edit
    fire = FakeToolHandler.holding({"fire_id": "fire-9"})
    main_model = ScriptedChatModel.replying(
        starting_the_scene_builder(),
        calling(tool_call("add_fire", "f1", scenario_id="other")),
        answer("The builder asks where the fire starts."),
    )
    rig = a_main_agent_with_subagents(main_model, a_scene_builder_that_asks(), add_fire=fire)
    turn = asyncio.ensure_future(collect(rig.main.run_turn("Make me a wildfire scene")))

    await until_held(fire, turn)

    # When the subagent asks its question while the main turn waits, and the wait ends
    await rig.subagent_job("j-2")
    fire.release()
    events = await turn

    # Then the main model read the question as a tagged notice, and the turn showed it
    asked = tagged(main_model.history_of_call(3), SUBAGENT_KIND)
    assert len(asked) == 1
    assert QUESTION in asked[0]
    assert "sa-1" in asked[0]
    assert SubagentMessage(subagent_id="sa-1", name="scene-builder", text=QUESTION) in events


async def test_a_subagent_message_while_the_main_agent_idles_comes_out_of_its_idle_events() -> None:
    # Given a scene builder started by a turn that has ended
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(starting_the_scene_builder(), answer("Started.")),
        a_scene_builder_that_asks(),
    )
    await collect(rig.main.run_turn("Make me a wildfire scene"))

    # When the subagent asks its question
    await rig.subagent_job("j-2")
    notice = await asyncio.wait_for(anext(rig.main.idle_events()), STEP_TIMEOUT_S)

    # Then the question is the first notice, naming the subagent
    assert notice == SubagentNotice(
        subagent_id="sa-1", name="scene-builder", message=QUESTION, text=notice.text
    )
    assert "message_subagent" in notice.text


# --- the main agent messages the subagent --------------------------------------------------


async def test_message_subagent_steers_a_running_subagent() -> None:
    # Given a scene builder holding on its first fire edit
    fire = FakeToolHandler.holding({"fire_id": "fire-1"})
    subagent = ScriptedChatModel.replying(
        calling(tool_call("add_fire", "c1", scenario_id="wildfire-1")),
        answer("Moved it downtown."),
    )
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(
            starting_the_scene_builder(),
            answer("Started."),
            calling(
                tool_call(
                    "message_subagent", "m1", subagent_id="sa-1", text="Make it a downtown block"
                )
            ),
            answer("Told it."),
        ),
        subagent,
        add_fire=fire,
    )
    await collect(rig.main.run_turn("Make me a wildfire scene"))
    await asyncio.wait_for(fire.started.wait(), STEP_TIMEOUT_S)

    # When the main agent messages it while it runs
    await collect(rig.main.run_turn("Make it downtown"))
    job = await rig.subagent_job("j-2")
    fire.release()

    # Then the message was delivered as a steer, the subagent read it last, and its turn finished
    assert result_of(rig.main_history, "m1") == {
        "subagent_id": "sa-1",
        "delivered": "STEER",
        "job_id": "j-2",
    }
    assert human_texts(subagent.history_of_call(2))[-1] == "Make it a downtown block"
    assert job.state is JobState.SUCCEEDED


async def test_message_subagent_on_a_finished_subagent_runs_a_follow_up_on_its_history() -> None:
    # Given a scene builder that finished its first turn
    subagent = ScriptedChatModel.replying(answer("Scene built."), answer("Rain added."))
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(
            starting_the_scene_builder(),
            answer("Started."),
            calling(tool_call("message_subagent", "m1", subagent_id="sa-1", text="Add rain too")),
            answer("Asked for rain."),
        ),
        subagent,
    )
    await collect(rig.main.run_turn("Make me a wildfire scene"))
    await rig.subagent_job("j-2")

    # When the main agent messages it
    await collect(rig.main.run_turn("And make it rain"))
    job = await rig.subagent_job("j-4")

    # Then a new turn ran as job j-4, on the subagent's whole history
    assert result_of(rig.main_history, "m1") == {
        "subagent_id": "sa-1",
        "delivered": "NEW_TURN",
        "job_id": "j-4",
    }
    assert human_texts(subagent.history_of_call(2)) == [TASK, "Add rain too"]
    assert job.result is not None
    assert job.result["reply"] == "Rain added."


async def test_message_subagent_naming_an_unknown_subagent_fails() -> None:
    # Given a main agent that messages a subagent it never started
    rig = a_main_agent_with_subagents(
        ScriptedChatModel.replying(
            calling(tool_call("message_subagent", "m1", subagent_id="sa-9", text="Hello")),
            answer("No such subagent."),
        ),
        ScriptedChatModel.replying(answer("Never said.")),
    )

    # When its turn runs
    await collect(rig.main.run_turn("Talk to the builder"))

    # Then the call failed naming the id
    failed = tool_message_for(rig.main_history, "m1")
    assert failed.status == "error"
    assert "sa-9" in str(failed.content)


# --- the chat server -----------------------------------------------------------------------


async def test_a_subagent_message_to_an_idle_conversation_opens_a_turn_on_the_watch_stream() -> (
    None
):
    # Given a conversation whose first turn has ended, watched for turns of its own
    model = ScriptedChatModel.replying(answer("Hello."), answer("The fire starts on the west."))
    async with a_chat_rig(model) as rig:
        await a_turn(rig, "Hi")
        watch = TurnStream.watching(rig)
        await eventually(lambda: rig.hub.watchers(CONVERSATION) == 1)

        # When a subagent messages the conversation while it idles
        runner = rig.hub.runner(CONVERSATION)
        assert runner is not None
        runner.notices.put_nowait(
            SubagentNotice(
                subagent_id="sa-1",
                name="scene-builder",
                message=QUESTION,
                text=f"Subagent sa-1 (scene-builder) says: {QUESTION}",
            )
        )
        events = await watch.turn()

    # Then the turn opens with the subagent's message and the model read it as a tagged notice
    opening = events[0]
    assert opening.WhichOneof("event") == "subagent_message"
    assert opening.subagent_message == chat_pb2.SubagentMessage(
        subagent_id="sa-1", name="scene-builder", text=QUESTION
    )
    assert tagged(model.history_of_call(2), SUBAGENT_KIND) == [
        f"Subagent sa-1 (scene-builder) says: {QUESTION}"
    ]
