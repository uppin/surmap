"""`ChatService` over a real `ChatHub`, in memory: streamed turns, steering, cancel, the watch
stream's job-event turns, the model list and history replay.

The model is n4's `ScriptedChatModel`; the SurMap tools are `FakeToolHandler`s bound to the real
`SurveyTools` contracts (see `tests/agent_server_fakes.py`), so only the server is under test.
"""

from __future__ import annotations

import asyncio
import json

from surmap.agent.llm.registry import ModelInfo
from surmap.agent.proto import chat_pb2, execution_pb2
from tests.agent_fakes import FakeToolHandler, ScriptedChatModel, answer, calling, tool_call
from tests.agent_server_fakes import (
    CONVERSATION,
    STEP_TIMEOUT_S,
    ChatRig,
    TurnStream,
    a_chat_rig,
    a_turn,
    eventually,
    finished_call,
    kinds,
    text_of,
)

DEMOS = {"scenes": [{"id": "euroc-v1-01-easy", "title": "EuRoC V1 01 easy"}]}


def a_model_listing_demos() -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(tool_call("list_demos", "call-1")), answer("One demo is ready to run")
    )


def a_model_running_a_demo_then(reply: str) -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(tool_call("run_demo", "call-1", dataset="euroc-v1-01-easy")), answer(reply)
    )


async def a_steered_turn(rig: ChatRig) -> tuple[chat_pb2.SteerResponse, list[chat_pb2.TurnEvent]]:
    """A turn blocked in `run_demo`, steered once the call is held; the steer's answer and
    the turn's events."""
    stream = TurnStream.of_turn(rig, "run the EuRoC demo")
    await asyncio.wait_for(rig.tool("run_demo").started.wait(), STEP_TIMEOUT_S)
    response = await rig.chat.unary(
        "Steer", chat_pb2.SteerRequest(conversation_id=CONVERSATION, text="use KITTI instead")
    )
    assert isinstance(response, chat_pb2.SteerResponse)
    return response, await stream.turn()


async def a_cancelled_turn(
    rig: ChatRig,
) -> tuple[chat_pb2.CancelTurnResponse, list[chat_pb2.TurnEvent]]:
    stream = TurnStream.of_turn(rig, "run the EuRoC demo")
    await asyncio.wait_for(rig.tool("run_demo").started.wait(), STEP_TIMEOUT_S)
    response = await rig.chat.unary(
        "CancelTurn", chat_pb2.CancelTurnRequest(conversation_id=CONVERSATION)
    )
    assert isinstance(response, chat_pb2.CancelTurnResponse)
    return response, await stream.turn()


async def a_job_event_turn(rig: ChatRig) -> list[chat_pb2.TurnEvent]:
    """A turn that starts `run_demo` as an async job and ends; then the job ends while the
    conversation idles, and the watch stream's turn is returned."""
    await a_turn(rig, "start the EuRoC demo in the background")
    watch = TurnStream.watching(rig)
    await eventually(lambda: rig.hub.watchers(CONVERSATION) == 1)
    rig.tool("run_demo").release()
    return await watch.turn()


def a_model_starting_an_async_run() -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(
            tool_call("run_demo", "call-1", dataset="euroc-v1-01-easy", execution={"mode": "ASYNC"})
        ),
        answer("run_demo started as job j-1"),
        answer("Job j-1 finished with 42 frames"),
    )


# --- a streamed turn -----------------------------------------------------------------------


async def test_a_turn_streams_the_message_the_tool_call_the_answer_and_its_end() -> None:
    # Given a model that lists the demos and then answers
    async with a_chat_rig(
        a_model_listing_demos(), list_demos=FakeToolHandler.returning(DEMOS)
    ) as rig:
        # When the user asks
        events = await a_turn(rig, "what demos can you run?")

    # Then the stream is the message, the call starting and finishing, the text, the end
    assert kinds(events) == [
        "user_message",
        "tool_call_started",
        "tool_call_finished",
        "text_delta",
        "turn_finished",
    ]


async def test_a_turn_streams_the_model_s_answer_text() -> None:
    # Given a model that lists the demos and then answers
    async with a_chat_rig(
        a_model_listing_demos(), list_demos=FakeToolHandler.returning(DEMOS)
    ) as rig:
        # When the user asks
        events = await a_turn(rig, "what demos can you run?")

    # Then the text deltas join into the model's answer
    assert text_of(events) == "One demo is ready to run"


async def test_a_finished_tool_call_carries_the_tool_s_result_as_json() -> None:
    # Given a model that lists the demos
    async with a_chat_rig(
        a_model_listing_demos(), list_demos=FakeToolHandler.returning(DEMOS)
    ) as rig:
        # When the user asks
        events = await a_turn(rig, "what demos can you run?")

    # Then the call succeeded with the tool's response
    finished = finished_call(events, "call-1")
    assert (finished.status, json.loads(finished.result_json)) == (
        chat_pb2.ToolCallFinished.SUCCEEDED,
        DEMOS,
    )


async def test_a_turn_ends_with_stop_when_the_model_answers() -> None:
    # Given a model that lists the demos and then answers
    async with a_chat_rig(
        a_model_listing_demos(), list_demos=FakeToolHandler.returning(DEMOS)
    ) as rig:
        # When the user asks
        events = await a_turn(rig, "what demos can you run?")

    # Then the last event finishes the turn with STOP
    assert events[-1].turn_finished.reason == chat_pb2.TurnFinished.STOP


async def test_every_event_is_numbered_in_order_from_one() -> None:
    # Given a model that lists the demos
    async with a_chat_rig(
        a_model_listing_demos(), list_demos=FakeToolHandler.returning(DEMOS)
    ) as rig:
        # When the user asks
        events = await a_turn(rig, "what demos can you run?")

    # Then seq runs 1, 2, 3, … with no gaps
    assert [event.seq for event in events] == list(range(1, len(events) + 1))


async def test_a_second_turn_continues_the_numbering_under_a_new_turn_id() -> None:
    # Given a conversation that has had one turn
    async with a_chat_rig(ScriptedChatModel.replying(answer("Hello"))) as rig:
        first = await a_turn(rig, "hi")

        # When the user writes again
        second = await a_turn(rig, "hi again")

    # Then the second turn's first event follows the first turn's last, under another turn id
    assert (second[0].seq, second[0].turn_id != first[0].turn_id) == (len(first) + 1, True)


# --- steering ------------------------------------------------------------------------------


async def test_a_steer_during_a_blocking_run_demo_is_accepted() -> None:
    # Given a turn blocked in run_demo
    async with a_chat_rig(
        a_model_running_a_demo_then("Switching to KITTI"), run_demo=FakeToolHandler.holding()
    ) as rig:
        # When the user steers it
        response, _ = await a_steered_turn(rig)

    # Then the steer was taken by the running turn
    assert response.accepted is True


async def test_a_steer_detaches_the_blocking_run_demo_to_a_running_job() -> None:
    # Given a turn blocked in run_demo
    async with a_chat_rig(
        a_model_running_a_demo_then("Switching to KITTI"), run_demo=FakeToolHandler.holding()
    ) as rig:
        # When the user steers it
        _, events = await a_steered_turn(rig)

    # Then the call finished as detached to job j-1, still running
    finished = finished_call(events, "call-1")
    assert (finished.status, finished.job.job_id, finished.job.status) == (
        chat_pb2.ToolCallFinished.DETACHED,
        "j-1",
        execution_pb2.RUNNING,
    )


async def test_a_steer_streams_steer_applied_naming_the_detached_call() -> None:
    # Given a turn blocked in run_demo
    async with a_chat_rig(
        a_model_running_a_demo_then("Switching to KITTI"), run_demo=FakeToolHandler.holding()
    ) as rig:
        # When the user steers it
        _, events = await a_steered_turn(rig)

    # Then the stream says the guidance joined the turn and which call it detached
    applied = [e.steer_applied for e in events if e.WhichOneof("event") == "steer_applied"]
    assert [(a.text, list(a.detached_call_ids)) for a in applied] == [
        ("use KITTI instead", ["call-1"])
    ]


async def test_the_model_s_reply_to_a_steer_streams_after_steer_applied() -> None:
    # Given a turn blocked in run_demo, and a model that answers the steer
    async with a_chat_rig(
        a_model_running_a_demo_then("Switching to KITTI"), run_demo=FakeToolHandler.holding()
    ) as rig:
        # When the user steers it
        _, events = await a_steered_turn(rig)

    # Then the reply comes after the steer, and the turn then ends
    assert kinds(events)[-3:] == ["steer_applied", "text_delta", "turn_finished"]


async def test_a_steer_with_no_turn_running_is_not_accepted() -> None:
    # Given a conversation whose turn has ended
    async with a_chat_rig(ScriptedChatModel.replying(answer("Hello"))) as rig:
        await a_turn(rig, "hi")

        # When the user steers it
        response = await rig.chat.unary(
            "Steer", chat_pb2.SteerRequest(conversation_id=CONVERSATION, text="faster")
        )

    # Then nothing took the guidance
    assert response == chat_pb2.SteerResponse(accepted=False)


# --- the watch stream ----------------------------------------------------------------------


async def test_a_job_that_ends_while_idle_starts_a_turn_on_the_watch_stream() -> None:
    # Given a turn that left run_demo running as an async job
    async with a_chat_rig(
        a_model_starting_an_async_run(), run_demo=FakeToolHandler.holding({"frames": 42})
    ) as rig:
        # When the job ends while the conversation is idle
        events = await a_job_event_turn(rig)

    # Then the watch stream carries the model's answer to it
    assert text_of(events) == "Job j-1 finished with 42 frames"


async def test_a_job_event_turn_opens_with_the_job_that_ended() -> None:
    # Given a turn that left run_demo running as an async job
    async with a_chat_rig(
        a_model_starting_an_async_run(), run_demo=FakeToolHandler.holding({"frames": 42})
    ) as rig:
        # When the job ends while the conversation is idle
        events = await a_job_event_turn(rig)

    # Then the turn's first event is that job's update, succeeded
    first = events[0].job_update
    assert (first.job_id, first.tool, first.status) == ("j-1", "run_demo", execution_pb2.SUCCEEDED)


# --- cancel --------------------------------------------------------------------------------


async def test_cancelling_a_running_turn_ends_it_as_cancelled() -> None:
    # Given a turn blocked in run_demo
    async with a_chat_rig(
        a_model_running_a_demo_then("never said"), run_demo=FakeToolHandler.holding()
    ) as rig:
        # When the user cancels it
        _, events = await a_cancelled_turn(rig)

    # Then the stream ends with turn_finished(CANCELLED)
    assert events[-1].turn_finished.reason == chat_pb2.TurnFinished.CANCELLED


async def test_cancelling_a_running_turn_reports_that_it_cancelled_one() -> None:
    # Given a turn blocked in run_demo
    async with a_chat_rig(
        a_model_running_a_demo_then("never said"), run_demo=FakeToolHandler.holding()
    ) as rig:
        # When the user cancels it
        response, _ = await a_cancelled_turn(rig)

    # Then the response says a turn was cancelled
    assert response == chat_pb2.CancelTurnResponse(cancelled=True)


async def test_cancelling_a_running_turn_cancels_its_blocking_tool_call() -> None:
    # Given a turn blocked in run_demo
    async with a_chat_rig(
        a_model_running_a_demo_then("never said"), run_demo=FakeToolHandler.holding()
    ) as rig:
        # When the user cancels it
        await a_cancelled_turn(rig)

        # Then the run_demo handler was cancelled too
        await eventually(lambda: rig.tool("run_demo").was_cancelled)


# --- models and history --------------------------------------------------------------------


async def test_list_models_names_the_reachable_models_and_the_default() -> None:
    # Given a server that can reach one Ollama model, its default
    llama = ModelInfo(id="ollama:llama3.2", provider="ollama", model="llama3.2")
    async with a_chat_rig(
        ScriptedChatModel.replying(answer("Hello")), models=(llama,), default_model_id=llama.id
    ) as rig:
        # When the UI lists the models
        response = await rig.chat.unary("ListModels", chat_pb2.ListModelsRequest())

    # Then that model is listed as available, and is the default
    assert response == chat_pb2.ListModelsResponse(
        models=[
            chat_pb2.ChatModel(
                id="ollama:llama3.2", provider="ollama", display_name="llama3.2", available=True
            )
        ],
        default_model_id="ollama:llama3.2",
    )


async def test_list_models_lists_an_unreachable_default_as_unavailable() -> None:
    # Given a server whose default model is Muse, with no Muse key and no Ollama models
    async with a_chat_rig(
        ScriptedChatModel.replying(answer("Hello")),
        models=(),
        default_model_id="meta:muse-wonder-1.0",
    ) as rig:
        # When the UI lists the models
        response = await rig.chat.unary("ListModels", chat_pb2.ListModelsRequest())

    # Then the default is still listed, marked unavailable
    assert isinstance(response, chat_pb2.ListModelsResponse)
    assert [(m.id, m.available) for m in response.models] == [("meta:muse-wonder-1.0", False)]


async def test_get_conversation_replays_every_streamed_event_in_order() -> None:
    # Given a conversation that has had a turn with a tool call
    async with a_chat_rig(
        a_model_listing_demos(), list_demos=FakeToolHandler.returning(DEMOS)
    ) as rig:
        streamed = await a_turn(rig, "what demos can you run?")

        # When a reloaded page reads the conversation
        response = await rig.chat.unary(
            "GetConversation", chat_pb2.GetConversationRequest(conversation_id=CONVERSATION)
        )

    # Then it gets exactly the events the stream delivered
    assert response == chat_pb2.GetConversationResponse(
        conversation_id=CONVERSATION, events=streamed
    )
