"""`ChatService` and `AgentJobs` refusals, and images on the chat stream, over a real `ChatHub`
in memory (see `tests/agent_server_fakes.py`)."""

from __future__ import annotations

import asyncio
import json

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import chat_pb2, jobs_pb2
from surmap.agent.server.binding import ToolImage
from surmap.agent.server.chat_service import CONVERSATION_HEADER
from tests.agent_fakes import FakeToolHandler, ScriptedChatModel, answer, calling, tool_call
from tests.agent_server_fakes import (
    CONVERSATION,
    STEP_TIMEOUT_S,
    TurnStream,
    a_chat_rig,
    a_jpeg,
    a_turn,
    finished_call,
)

FRAME_JPEG = a_jpeg()


def a_model_running_a_demo() -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(tool_call("run_demo", "call-1", dataset="euroc-v1-01-easy")), answer("Done")
    )


def a_model_starting_an_async_run() -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(
            tool_call("run_demo", "call-1", dataset="euroc-v1-01-easy", execution={"mode": "ASYNC"})
        ),
        answer("run_demo started as job j-1"),
    )


def a_model_looking_at_a_frame() -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(tool_call("get_frame", "call-1", run_id="run-7")), answer("A box on a table")
    )


def a_frame_tool() -> FakeToolHandler:
    return FakeToolHandler.returning(
        {"width": 64, "height": 48, "image": ToolImage(FRAME_JPEG, "image/jpeg")}
    )


# --- StreamTurn refusals -------------------------------------------------------------------


async def test_a_turn_on_a_model_no_provider_builds_is_an_invalid_argument() -> None:
    # Given a server whose providers are meta and ollama
    async with a_chat_rig(ScriptedChatModel.replying(answer("Hello"))) as rig:
        # When a turn names another provider's model
        with pytest.raises(ConnectError) as refused:
            await a_turn(rig, "hi", model_id="gpt:4o")

    # Then it is refused as an invalid argument
    assert refused.value.code == Code.INVALID_ARGUMENT


async def test_a_turn_while_another_runs_is_a_failed_precondition() -> None:
    # Given a turn blocked in run_demo
    async with a_chat_rig(a_model_running_a_demo(), run_demo=FakeToolHandler.holding()) as rig:
        TurnStream.of_turn(rig, "run the EuRoC demo")
        await asyncio.wait_for(rig.tool("run_demo").started.wait(), STEP_TIMEOUT_S)

        # When a second turn starts on the same conversation
        with pytest.raises(ConnectError) as refused:
            await a_turn(rig, "and another")

    # Then it is refused until the first one ends
    assert refused.value.code == Code.FAILED_PRECONDITION


async def test_cancelling_with_no_turn_running_cancels_nothing() -> None:
    # Given a conversation whose turn has ended
    async with a_chat_rig(ScriptedChatModel.replying(answer("Hello"))) as rig:
        await a_turn(rig, "hi")

        # When the user cancels
        response = await rig.chat.unary(
            "CancelTurn", chat_pb2.CancelTurnRequest(conversation_id=CONVERSATION)
        )

    # Then nothing was cancelled
    assert response == chat_pb2.CancelTurnResponse(cancelled=False)


async def test_reading_a_conversation_that_never_started_is_not_found() -> None:
    # Given a server with no conversations
    async with a_chat_rig(ScriptedChatModel.replying(answer("Hello"))) as rig:
        # When a page reads a conversation id it made up
        with pytest.raises(ConnectError) as refused:
            await rig.chat.unary(
                "GetConversation", chat_pb2.GetConversationRequest(conversation_id="conv-404")
            )

    # Then there is no such conversation
    assert refused.value.code == Code.NOT_FOUND


# --- images --------------------------------------------------------------------------------


async def test_a_tool_s_image_reaches_the_stream_as_jpeg_bytes() -> None:
    # Given a model that looks at a frame
    async with a_chat_rig(a_model_looking_at_a_frame(), get_frame=a_frame_tool()) as rig:
        # When the user asks
        events = await a_turn(rig, "what is in run-7's first frame?")

    # Then the finished call carries the frame's bytes and media type
    finished = finished_call(events, "call-1")
    assert (finished.image, finished.media_type) == (FRAME_JPEG, "image/jpeg")


async def test_a_tool_s_image_is_kept_out_of_the_result_json() -> None:
    # Given a model that looks at a frame
    async with a_chat_rig(a_model_looking_at_a_frame(), get_frame=a_frame_tool()) as rig:
        # When the user asks
        events = await a_turn(rig, "what is in run-7's first frame?")

    # Then the result JSON has the frame's size but not the image
    assert json.loads(finished_call(events, "call-1").result_json) == {"width": 64, "height": 48}


# --- AgentJobs -----------------------------------------------------------------------------


async def test_get_job_reads_the_job_of_the_conversation_the_header_names() -> None:
    # Given a turn that left run_demo running as job j-1
    async with a_chat_rig(
        a_model_starting_an_async_run(), run_demo=FakeToolHandler.holding()
    ) as rig:
        await a_turn(rig, "start the EuRoC demo in the background")

        # When the UI reads j-1 for that conversation
        response = await rig.jobs.unary(
            "GetJob",
            jobs_pb2.GetJobRequest(job_id="j-1"),
            headers={CONVERSATION_HEADER: CONVERSATION},
        )

    # Then it is the run_demo job
    assert isinstance(response, jobs_pb2.GetJobResponse)
    assert (response.job.job.job_id, response.job.job.tool) == ("j-1", "run_demo")


async def test_a_jobs_call_without_the_conversation_header_is_an_invalid_argument() -> None:
    # Given a server with a conversation
    async with a_chat_rig(ScriptedChatModel.replying(answer("Hello"))) as rig:
        await a_turn(rig, "hi")

        # When the UI lists jobs without naming the conversation
        with pytest.raises(ConnectError) as refused:
            await rig.jobs.unary("ListJobs", jobs_pb2.ListJobsRequest())

    # Then it is refused as an invalid argument
    assert refused.value.code == Code.INVALID_ARGUMENT
