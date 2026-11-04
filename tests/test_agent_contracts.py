"""Tool contracts built from the `surmap.agent.v1` descriptors: names, descriptions, schemas
and execution policies a model binds."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from google.protobuf.descriptor import ServiceDescriptor

from surmap.agent.contracts import (
    ExecutionMode,
    ExecutionPolicy,
    OnTimeout,
    ToolContract,
    resolve_execution,
    tool_contracts,
)
from surmap.agent.proto import chat_pb2, jobs_pb2, survey_tools_pb2
from tests.agent_schema import admits, property_names, property_of, required_of

SURVEY_TOOLS = survey_tools_pb2.DESCRIPTOR.services_by_name["SurveyTools"]
AGENT_JOBS = jobs_pb2.DESCRIPTOR.services_by_name["AgentJobs"]
CHAT_SERVICE = chat_pb2.DESCRIPTOR.services_by_name["ChatService"]

SYNC = ExecutionMode.SYNC
FAIL = OnTimeout.FAIL
DETACH = OnTimeout.DETACH


def names_of(service: ServiceDescriptor) -> tuple[str, ...]:
    return tuple(contract.name for contract in tool_contracts(service))


def every_tool() -> tuple[ToolContract, ...]:
    return (*tool_contracts(SURVEY_TOOLS), *tool_contracts(AGENT_JOBS))


def the_tool(name: str) -> ToolContract:
    return {contract.name: contract for contract in every_tool()}[name]


def offers_optional_execution(contract: ToolContract) -> bool:
    schema = contract.input_schema
    return "execution" in property_names(schema) and "execution" not in required_of(schema)


def a_policy(mode: ExecutionMode, timeout_s: int, on_timeout: OnTimeout) -> ExecutionPolicy:
    return ExecutionPolicy(mode=mode, timeout_s=timeout_s, on_timeout=on_timeout)


def run_demo_with(**arguments: object) -> Mapping[str, object]:
    return {"dataset": "euroc-v1-01-easy", **arguments}


def test_every_survey_tools_rpc_is_a_tool_named_in_snake_case() -> None:
    # Given the SurveyTools service from the agent protos
    service = SURVEY_TOOLS

    # When its tool contracts are built
    names = names_of(service)

    # Then each rpc is one tool, named in snake_case, in declaration order
    assert names == (
        "list_demos",
        "list_onboard_models",
        "run_demo",
        "get_run",
        "prompt_sam",
        "find_objects",
        "get_object",
        "get_object_geometry",
        "get_frame",
        "list_datasets",
        "get_dataset",
        "prepare_dataset",
        "run_rtabmap",
        "run_sam_on_dataset",
    )


def test_every_agent_jobs_rpc_is_a_tool_named_in_snake_case() -> None:
    # Given the AgentJobs service from the agent protos
    service = AGENT_JOBS

    # When its tool contracts are built
    names = names_of(service)

    # Then each rpc is one tool, named in snake_case
    assert names == ("wait_for_jobs", "get_job", "cancel_job", "list_jobs")


def test_a_tool_contract_names_the_service_and_rpc_it_calls() -> None:
    # When the run_demo contract is built
    contract = the_tool("run_demo")

    # Then it calls SurveyTools.RunDemo
    assert (contract.service, contract.method) == ("surmap.agent.v1.SurveyTools", "RunDemo")


def test_a_tool_description_is_its_rpcs_leading_comment() -> None:
    # When the list_demos contract is built
    contract = the_tool("list_demos")

    # Then its description is the comment above ListDemos, as one line of text
    assert contract.description == (
        "Lists the demo scenes this station can run, with their default SAM prompt and whether "
        "their data is prepared."
    )


def test_every_tool_has_a_description() -> None:
    # When every tool contract is built
    contracts = every_tool()

    # Then none is left without a description for the model
    assert [contract.name for contract in contracts if not contract.description] == []


def test_each_tool_carries_the_default_execution_its_rpc_declares() -> None:
    # When every tool contract is built
    defaults = {contract.name: contract.default_execution for contract in every_tool()}

    # Then long-running tools detach to a job after their timeout; quick reads fail instead
    assert defaults == {
        "list_demos": a_policy(SYNC, 10, FAIL),
        "list_onboard_models": a_policy(SYNC, 10, FAIL),
        "run_demo": a_policy(SYNC, 30, DETACH),
        "get_run": a_policy(SYNC, 10, FAIL),
        "prompt_sam": a_policy(SYNC, 60, DETACH),
        "find_objects": a_policy(SYNC, 15, FAIL),
        "get_object": a_policy(SYNC, 10, FAIL),
        "get_object_geometry": a_policy(SYNC, 15, FAIL),
        "get_frame": a_policy(SYNC, 15, FAIL),
        "list_datasets": a_policy(SYNC, 10, FAIL),
        "get_dataset": a_policy(SYNC, 10, FAIL),
        "prepare_dataset": a_policy(SYNC, 30, DETACH),
        "run_rtabmap": a_policy(SYNC, 30, DETACH),
        "run_sam_on_dataset": a_policy(SYNC, 60, DETACH),
        "wait_for_jobs": a_policy(SYNC, 300, FAIL),
        "get_job": a_policy(SYNC, 10, FAIL),
        "cancel_job": a_policy(SYNC, 10, FAIL),
        "list_jobs": a_policy(SYNC, 10, FAIL),
    }


def test_run_demos_schema_accepts_a_dataset_and_a_prompt() -> None:
    # Given the run_demo tool's argument schema
    schema = the_tool("run_demo").input_schema

    # When the model asks for a scene with a SAM prompt
    accepted = admits(schema, {"dataset": "kitti-2011-09-26-drive-0009", "prompt": "car"})

    # Then the arguments are valid
    assert accepted is True


def test_run_demos_schema_rejects_an_unknown_field() -> None:
    # Given the run_demo tool's argument schema
    schema = the_tool("run_demo").input_schema

    # When the model passes an argument the request does not have
    accepted = admits(schema, run_demo_with(colour="red"))

    # Then the arguments are refused
    assert accepted is False


def test_run_demos_schema_requires_only_the_dataset() -> None:
    # When the run_demo contract is built
    schema = the_tool("run_demo").input_schema

    # Then the dataset is required and the optional prompt, frames and rate are not
    assert required_of(schema) == ["dataset"]


def test_an_argument_is_described_by_its_field_comment() -> None:
    # Given the run_demo tool's argument schema
    schema = the_tool("run_demo").input_schema

    # When the dataset argument is read
    dataset = property_of(schema, "dataset")

    # Then its description is the comment above RunDemoRequest.dataset
    assert dataset["description"] == "The scene to run: a DemoScene id from list_demos."


def test_an_enum_argument_is_a_string_enum_of_its_named_values() -> None:
    # Given the wait_for_jobs tool's argument schema
    schema = the_tool("wait_for_jobs").input_schema

    # When the mode argument is read
    mode = property_of(schema, "mode")

    # Then the model writes the value's name, and the unspecified zero value is not offered
    assert (mode["type"], mode["enum"]) == ("string", ["ALL", "ANY"])


def test_a_repeated_argument_is_an_array_of_its_element_type() -> None:
    # Given the prompt_sam tool's argument schema
    schema = the_tool("prompt_sam").input_schema

    # When the frame ids argument is read
    frame_ids = property_of(schema, "frame_ids")

    # Then it is a list of integer frame ids
    assert (frame_ids["type"], frame_ids["items"]) == ("array", {"type": "integer"})


def test_a_message_argument_is_a_nested_object() -> None:
    # Given the find_objects tool's argument schema
    schema = the_tool("find_objects").input_schema

    # When the model searches around a point in the run's object frame
    accepted = admits(
        schema, {"run_id": "run-7", "near": {"x": 1.5, "y": 2.0, "z": 0.0}, "radius_m": 3.0}
    )

    # Then the nested point is valid
    assert accepted is True


def test_oneof_members_are_optional_arguments() -> None:
    # When the get_frame contract is built
    schema = the_tool("get_frame").input_schema

    # Then only the run is required: frame index, id or time, and the crop, are choices
    assert required_of(schema) == ["run_id"]


def test_every_tool_offers_an_optional_execution_argument() -> None:
    # When every tool contract is built
    contracts = every_tool()

    # Then each schema has an execution property the model may leave out
    assert [
        contract.name for contract in contracts if not offers_optional_execution(contract)
    ] == []


def test_the_execution_argument_names_mode_timeout_and_on_timeout() -> None:
    # Given the run_demo tool's argument schema
    schema = the_tool("run_demo").input_schema

    # When its execution argument is read
    execution = property_of(schema, "execution")

    # Then it overrides the mode, timeout and post-timeout policy, and nothing else
    assert (
        property_of(execution, "mode")["enum"],
        property_of(execution, "timeout_s")["type"],
        property_of(execution, "on_timeout")["enum"],
        execution["additionalProperties"],
    ) == (["SYNC", "ASYNC"], "integer", ["FAIL", "DETACH"], False)


def test_a_well_formed_execution_override_is_valid_arguments() -> None:
    # Given the run_demo tool's argument schema
    schema = the_tool("run_demo").input_schema

    # When the model asks for the run as a job straight away
    accepted = admits(
        schema, run_demo_with(execution={"mode": "ASYNC", "timeout_s": 0, "on_timeout": "FAIL"})
    )

    # Then the arguments are valid
    assert accepted is True


def test_an_unknown_execution_mode_is_refused_by_the_schema() -> None:
    # Given the run_demo tool's argument schema
    schema = the_tool("run_demo").input_schema

    # When the model names a mode that does not exist
    accepted = admits(schema, run_demo_with(execution={"mode": "LATER"}))

    # Then the arguments are refused
    assert accepted is False


def test_a_call_without_execution_runs_with_the_rpcs_default() -> None:
    # Given the run_demo tool, which detaches to a job after 30 s by default
    contract = the_tool("run_demo")

    # When the model calls it without an execution argument
    policy = resolve_execution(contract, run_demo_with(prompt="box"))

    # Then the call runs with the declared default
    assert policy == a_policy(SYNC, 30, DETACH)


def test_a_call_with_a_full_execution_override_runs_with_the_override() -> None:
    # Given the run_demo tool
    contract = the_tool("run_demo")

    # When the model asks for the run as a job straight away
    policy = resolve_execution(
        contract, run_demo_with(execution={"mode": "ASYNC", "timeout_s": 0, "on_timeout": "FAIL"})
    )

    # Then the call runs as asked
    assert policy == a_policy(ExecutionMode.ASYNC, 0, FAIL)


def test_a_partial_execution_override_keeps_the_default_for_what_it_leaves_out() -> None:
    # Given the run_demo tool, SYNC for 30 s then DETACH by default
    contract = the_tool("run_demo")

    # When the model only lengthens the timeout
    policy = resolve_execution(contract, run_demo_with(execution={"timeout_s": 120}))

    # Then the call still runs SYNC and detaches, after 120 s
    assert policy == a_policy(SYNC, 120, DETACH)


def test_an_execution_override_with_an_unknown_mode_is_an_error() -> None:
    # Given the run_demo tool
    contract = the_tool("run_demo")

    # When the model names a mode that does not exist
    # Then the call is refused before it runs
    with pytest.raises(ValueError, match="LATER"):
        resolve_execution(contract, run_demo_with(execution={"mode": "LATER"}))


def test_a_service_whose_rpcs_declare_no_default_execution_has_no_tool_contracts() -> None:
    # Given the browser-facing ChatService, whose rpcs are not tools
    service = CHAT_SERVICE

    # When tool contracts are built from it
    # Then the builder refuses, naming an rpc with no default_execution
    with pytest.raises(ValueError, match="StreamTurn"):
        tool_contracts(service)
