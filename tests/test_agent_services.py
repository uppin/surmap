"""The survey agent's service modules mounted in memory: what each serves, and how an rpc
without a handler answers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from google.protobuf.message import Message

from surmap.agent.proto import chat_pb2, jobs_pb2, survey_tools_pb2
from surmap.agent.services import (
    agent_jobs_module,
    chat_service_module,
    survey_tools_module,
)
from surmap.rpc.compose import CompositionError
from surmap.rpc.description import ServerDescription, ServiceModule
from surmap.rpc.hosts.in_memory import InMemoryHost, ServiceClient

SURVEY_TOOLS = survey_tools_pb2.DESCRIPTOR.services_by_name["SurveyTools"]
AGENT_JOBS = jobs_pb2.DESCRIPTOR.services_by_name["AgentJobs"]
CHAT_SERVICE = chat_pb2.DESCRIPTOR.services_by_name["ChatService"]


def a_host(module: ServiceModule[Any]) -> InMemoryHost[None]:
    return InMemoryHost(ServerDescription(services=(module,)), None)


async def get_run_echoing_its_id(
    request: survey_tools_pb2.GetRunRequest, _ctx: object
) -> survey_tools_pb2.GetRunResponse:
    return survey_tools_pb2.GetRunResponse(
        run=survey_tools_pb2.RunInfo(run_id=request.run_id, dataset="euroc-v1-01-easy")
    )


async def a_turn_that_says_hello(
    request: chat_pb2.StreamTurnRequest, _ctx: object
) -> AsyncIterator[chat_pb2.TurnEvent]:
    yield chat_pb2.TurnEvent(conversation_id=request.conversation_id, seq=1, text_delta="hello")
    yield chat_pb2.TurnEvent(
        conversation_id=request.conversation_id,
        seq=2,
        turn_finished=chat_pb2.TurnFinished(reason=chat_pb2.TurnFinished.STOP),
    )


async def events_of(stream: AsyncIterator[Message]) -> list[chat_pb2.TurnEvent]:
    return [chat_pb2.TurnEvent.FromString(event.SerializeToString()) async for event in stream]


def test_the_survey_tools_module_mounts_on_an_in_memory_host() -> None:
    # Given the SurveyTools module with no handlers yet
    module = survey_tools_module({})

    # When it is mounted in memory
    host = a_host(module)

    # Then the host serves SurveyTools
    assert isinstance(host.client(SURVEY_TOOLS), ServiceClient)


def test_the_agent_jobs_module_mounts_on_an_in_memory_host() -> None:
    # Given the AgentJobs module with no handlers yet
    module = agent_jobs_module({})

    # When it is mounted in memory
    host = a_host(module)

    # Then the host serves AgentJobs
    assert isinstance(host.client(AGENT_JOBS), ServiceClient)


def test_the_chat_service_module_mounts_on_an_in_memory_host() -> None:
    # Given the ChatService module with no handlers yet
    module = chat_service_module({})

    # When it is mounted in memory
    host = a_host(module)

    # Then the host serves ChatService
    assert isinstance(host.client(CHAT_SERVICE), ServiceClient)


async def test_a_survey_tool_without_a_handler_answers_unimplemented() -> None:
    # Given SurveyTools mounted with no ListDemos handler
    client = a_host(survey_tools_module({})).client(SURVEY_TOOLS)

    # When a client lists the demos
    with pytest.raises(ConnectError) as error:
        await client.unary("ListDemos", survey_tools_pb2.ListDemosRequest())

    # Then the call answers UNIMPLEMENTED
    assert error.value.code == Code.UNIMPLEMENTED


async def test_a_job_tool_without_a_handler_answers_unimplemented() -> None:
    # Given AgentJobs mounted with no WaitForJobs handler
    client = a_host(agent_jobs_module({})).client(AGENT_JOBS)

    # When a client waits for a job
    with pytest.raises(ConnectError) as error:
        await client.unary("WaitForJobs", jobs_pb2.WaitForJobsRequest(job_ids=["job-1"]))

    # Then the call answers UNIMPLEMENTED
    assert error.value.code == Code.UNIMPLEMENTED


async def test_a_chat_stream_without_a_handler_answers_unimplemented() -> None:
    # Given ChatService mounted with no StreamTurn handler
    client = a_host(chat_service_module({})).client(CHAT_SERVICE)

    # When a client starts a turn
    request = chat_pb2.StreamTurnRequest(conversation_id="conv-1", text="list the demos")
    with pytest.raises(ConnectError) as error:
        await events_of(client.server_stream("StreamTurn", request))

    # Then the stream answers UNIMPLEMENTED
    assert error.value.code == Code.UNIMPLEMENTED


async def test_a_supplied_tool_handler_answers_with_the_decoded_request() -> None:
    # Given SurveyTools mounted with a GetRun handler
    client = a_host(survey_tools_module({"GetRun": get_run_echoing_its_id})).client(SURVEY_TOOLS)

    # When a client asks for run-7
    reply = await client.unary("GetRun", survey_tools_pb2.GetRunRequest(run_id="run-7"))

    # Then the handler saw run-7 and its answer reaches the client
    answer = survey_tools_pb2.GetRunResponse.FromString(reply.SerializeToString())
    assert answer.run.run_id == "run-7"


async def test_a_supplied_chat_handler_streams_the_turns_events() -> None:
    # Given ChatService mounted with a StreamTurn handler that says hello and stops
    client = a_host(chat_service_module({"StreamTurn": a_turn_that_says_hello})).client(
        CHAT_SERVICE
    )

    # When a client starts a turn
    request = chat_pb2.StreamTurnRequest(conversation_id="conv-1", text="hi")
    events = await events_of(client.server_stream("StreamTurn", request))

    # Then it receives the text and the turn's end, in order
    assert [event.WhichOneof("event") for event in events] == ["text_delta", "turn_finished"]


def test_a_handler_for_an_rpc_the_service_lacks_fails_at_mount() -> None:
    # Given SurveyTools with a handler under a misspelt rpc name
    module = survey_tools_module({"RunDemos": get_run_echoing_its_id})

    # When it is mounted
    # Then mounting refuses, naming the unknown rpc
    with pytest.raises(CompositionError) as error:
        a_host(module)
    assert error.value.unknown == ("RunDemos",)
