"""`agent_tools`: the `SurveyTools` handlers (connect-shape, protos in and out) and the job
tools, bound as the tools a conversation's model calls.

The handlers here are small proto fakes, so the SurMap tools themselves (n7) are not involved.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.runtime.jobs import Completed, Failed, JobRunner, ToolOutcome
from surmap.agent.runtime.tools import BoundTool
from surmap.agent.server.binding import IMAGE_KEY, ToolImage, agent_tools
from surmap.agent.services import Handler
from tests.agent_server_fakes import JOB_CONTRACTS, SURVEY_CONTRACTS, a_jpeg

FRAME_JPEG = a_jpeg()


async def a_run_echoing_its_id(request: pb.GetRunRequest, _ctx: object) -> pb.GetRunResponse:
    return pb.GetRunResponse(
        run=pb.RunInfo(
            run_id=request.run_id,
            dataset="euroc-v1-01-easy",
            prompt="box",
            frames=42,
            objects=0,
            status=pb.RunInfo.FINISHED,
        )
    )


async def no_such_run(request: pb.GetRunRequest, _ctx: object) -> pb.GetRunResponse:
    raise ConnectError(Code.NOT_FOUND, f"no run {request.run_id}")


async def a_frame(request: pb.GetFrameRequest, _ctx: object) -> pb.GetFrameResponse:
    return pb.GetFrameResponse(width=64, height=48, image=FRAME_JPEG, media_type="image/jpeg")


async def unimplemented(_request: object, _ctx: object) -> None:
    raise ConnectError(Code.UNIMPLEMENTED, "not in this test")


def survey_handlers(**overrides: Handler) -> Mapping[str, Handler]:
    """A handler for every `SurveyTools` rpc, `UNIMPLEMENTED` unless overridden by rpc name."""
    return {
        contract.method: overrides.get(contract.method, unimplemented)
        for contract in SURVEY_CONTRACTS
    }


def the_tools(runner: JobRunner, **overrides: Handler) -> dict[str, BoundTool]:
    bound = agent_tools((*SURVEY_CONTRACTS, *JOB_CONTRACTS), survey_handlers(**overrides), runner)
    return {tool.name: tool for tool in bound}


async def calling(tool: BoundTool, **arguments: object) -> ToolOutcome:
    return await tool.run(tool.prepare(arguments))


def test_every_survey_tool_and_every_job_tool_is_bound() -> None:
    # Given a handler for every SurveyTools rpc
    runner = JobRunner()

    # When the tools are bound
    tools = the_tools(runner)

    # Then the model can call each SurveyTools rpc and the four job tools by name
    assert sorted(tools) == sorted(
        [contract.name for contract in SURVEY_CONTRACTS]
        + ["wait_for_jobs", "get_job", "cancel_job", "list_jobs"]
    )


def test_every_bound_tool_runs_on_the_conversation_s_runner() -> None:
    # Given one conversation's runner
    runner = JobRunner()

    # When the tools are bound
    tools = the_tools(runner)

    # Then every tool, survey or job, runs its calls there
    assert {id(tool.runner) for tool in tools.values()} == {id(runner)}


def test_a_survey_rpc_without_a_handler_is_refused() -> None:
    # Given handlers that leave out GetFrame
    handlers = {name: handler for name, handler in survey_handlers().items() if name != "GetFrame"}

    # When the tools are bound
    # Then binding names the missing rpc
    with pytest.raises(ValueError, match="GetFrame"):
        agent_tools((*SURVEY_CONTRACTS, *JOB_CONTRACTS), handlers, JobRunner())


async def test_a_call_s_arguments_reach_the_handler_as_its_request_message() -> None:
    # Given get_run bound to a handler that echoes the run id
    tool = the_tools(JobRunner(), GetRun=a_run_echoing_its_id)["get_run"]

    # When the model calls it for run-7
    outcome = await calling(tool, run_id="run-7")

    # Then the response comes back as JSON, defaults included
    assert isinstance(outcome, Completed)
    assert outcome.result["run"] == {
        "run_id": "run-7",
        "dataset": "euroc-v1-01-easy",
        "prompt": "box",
        "frames": 42,
        "objects": 0,
        "status": "FINISHED",
    }


async def test_a_handler_s_connect_error_fails_the_call_with_its_message() -> None:
    # Given get_run bound to a handler that has no such run
    tool = the_tools(JobRunner(), GetRun=no_such_run)["get_run"]

    # When the model asks for run-404
    outcome = await calling(tool, run_id="run-404")

    # Then the call failed, saying why
    assert isinstance(outcome, Failed)
    assert "no run run-404" in outcome.error


async def test_arguments_the_request_cannot_hold_fail_the_call() -> None:
    # Given get_run bound to a working handler
    tool = the_tools(JobRunner(), GetRun=a_run_echoing_its_id)["get_run"]

    # When the model passes a field GetRunRequest does not have
    outcome = await calling(tool, run_name="run-7")

    # Then the call failed rather than reaching the handler
    assert isinstance(outcome, Failed)


async def test_a_response_image_comes_back_as_a_tool_image() -> None:
    # Given get_frame bound to a handler that returns a JPEG
    tool = the_tools(JobRunner(), GetFrame=a_frame)["get_frame"]

    # When the model calls it
    outcome = await calling(tool, run_id="run-7")

    # Then the bytes come back as a ToolImage, not inside the JSON
    assert isinstance(outcome, Completed)
    assert outcome.result[IMAGE_KEY] == ToolImage(FRAME_JPEG, "image/jpeg")


def test_the_model_reads_an_image_as_a_one_line_placeholder() -> None:
    # Given a 4-byte JPEG a tool returned
    image = ToolImage(b"\xff\xd8\xff\xd9", "image/jpeg")

    # When the model's tool message renders it
    text = str(image)

    # Then it reads the media type and size, not the bytes
    assert text == "<image/jpeg, 4 bytes, shown to the user>"
