"""Tool results saved to a file: on request (`output.to_file`) or when they are over the inline
limit. The model then reads a short reference instead of the whole result. A scripted model
drives a real session and runner, and the files land under `tmp_path`."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from langchain_core.messages import ToolMessage

from surmap.agent.contracts import ExecutionMode, ToolContract, tool_contracts
from surmap.agent.proto import survey_tools_pb2
from surmap.agent.runtime.outputs import ToolOutputs
from tests.agent_fakes import (
    FakeToolHandler,
    ScriptedChatModel,
    a_session,
    a_tool_contract,
    answer,
    calling,
    collect,
    tool_call,
    tool_message_for,
)
from tests.agent_server_fakes import STEP_TIMEOUT_S

LIST_ASSETS = a_tool_contract("list_assets", timeout_s=1)
SEARCH = a_tool_contract("search_assets", mode=ExecutionMode.ASYNC, timeout_s=1)

SMALL_RESULT: dict[str, object] = {"assets": ["crate", "barrel"]}
LARGE_RESULT: dict[str, object] = {
    "assets": [{"id": f"asset-{n}", "title": f"Debris pile {n}"} for n in range(400)]
}
LIMIT = 2_000
"""Bytes of inline JSON a result may be before it is saved; `LARGE_RESULT` is far over it."""


def outputs_in(tmp_path: Path, max_inline_bytes: int = LIMIT) -> ToolOutputs:
    return ToolOutputs(directory=tmp_path / "outputs", max_inline_bytes=max_inline_bytes)


def reference_in(message: ToolMessage) -> dict[str, object]:
    """The saved-file reference a tool message carries in place of the result."""
    content = json.loads(message.text)
    assert isinstance(content, dict) and "saved_to_file" in content, message.text
    return content


def saved_result(reference: dict[str, object]) -> object:
    return json.loads(Path(str(reference["saved_to_file"])).read_text(encoding="utf-8"))


async def a_turn_calling_list_assets(
    tmp_path: Path, result: dict[str, object], **arguments: object
) -> ToolMessage:
    """The tool message the model reads after one `list_assets` call returning `result`."""
    model = ScriptedChatModel.replying(
        calling(tool_call("list_assets", "call-1", **arguments)), answer("Done.")
    )
    rig = a_session(
        model, (LIST_ASSETS, FakeToolHandler.returning(result)), outputs=outputs_in(tmp_path)
    )
    await collect(rig.session.run_turn("Which assets are there?"))
    return tool_message_for(model.history_of_call(2), "call-1")


# --- acceptance: saving on request and over the limit ------------------------------------


async def test_a_call_asking_for_a_file_gets_a_reference_and_the_file_holds_the_result(
    tmp_path: Path,
) -> None:
    # Given a small result, well under the inline limit
    # When the model asks for it as a file
    message = await a_turn_calling_list_assets(tmp_path, SMALL_RESULT, output={"to_file": True})

    # Then it reads a reference, and the referenced file holds the whole result
    reference = reference_in(message)
    assert reference["reason"] == "requested"
    assert saved_result(reference) == SMALL_RESULT


async def test_a_result_over_the_inline_limit_is_saved_without_being_asked(
    tmp_path: Path,
) -> None:
    # Given a result far over the inline limit
    # When the model calls the tool plainly
    message = await a_turn_calling_list_assets(tmp_path, LARGE_RESULT)

    # Then the model reads a short reference instead, and the file holds the whole result
    reference = reference_in(message)
    assert str(reference["reason"]).startswith("over the inline limit")
    assert len(message.text) < LIMIT
    assert saved_result(reference) == LARGE_RESULT


async def test_a_result_under_the_inline_limit_stays_inline(tmp_path: Path) -> None:
    # Given a small result
    # When the model calls the tool plainly
    message = await a_turn_calling_list_assets(tmp_path, SMALL_RESULT)

    # Then the result is the message itself
    assert json.loads(message.text) == SMALL_RESULT


async def test_the_reference_gives_size_line_count_and_a_preview_of_the_file(
    tmp_path: Path,
) -> None:
    # Given a result far over the inline limit
    # When the model calls the tool
    reference = reference_in(await a_turn_calling_list_assets(tmp_path, LARGE_RESULT))

    # Then the reference says how big the file is and shows its start
    saved = Path(str(reference["saved_to_file"])).read_text(encoding="utf-8")
    assert reference["bytes"] == len(saved.encode("utf-8"))
    assert reference["lines"] == len(saved.splitlines())
    assert saved.startswith(str(reference["preview"]))
    assert "read_file" in str(reference["hint"]) and "grep_files" in str(reference["hint"])


async def test_a_saved_result_is_pretty_printed_so_it_reads_and_greps_by_line(
    tmp_path: Path,
) -> None:
    # Given a result far over the inline limit
    # When the model calls the tool
    reference = reference_in(await a_turn_calling_list_assets(tmp_path, LARGE_RESULT))

    # Then each asset id sits on a line of its own
    lines = Path(str(reference["saved_to_file"])).read_text(encoding="utf-8").splitlines()
    assert sum('"id": "asset-' in line for line in lines) == 400


async def test_the_handler_never_sees_the_output_argument(tmp_path: Path) -> None:
    # Given a tool handler that records what it is called with
    handler = FakeToolHandler.returning(SMALL_RESULT)
    model = ScriptedChatModel.replying(
        calling(tool_call("list_assets", "call-1", output={"to_file": True})), answer("Done.")
    )
    rig = a_session(model, (LIST_ASSETS, handler), outputs=outputs_in(tmp_path))

    # When the model calls it asking for a file
    await collect(rig.session.run_turn("Which assets are there?"))

    # Then the handler got no output argument
    assert handler.calls == [{}]


async def test_an_output_that_is_not_an_object_fails_the_call_as_invalid_arguments(
    tmp_path: Path,
) -> None:
    # Given a model passing output as a bare flag
    # When the call runs
    message = await a_turn_calling_list_assets(tmp_path, SMALL_RESULT, output=True)

    # Then the call fails before running, naming the argument
    assert message.status == "error"
    assert "Invalid arguments" in message.text and "output" in message.text


async def test_without_a_directory_every_result_stays_inline() -> None:
    # Given a session whose runner has nowhere to save results
    model = ScriptedChatModel.replying(calling(tool_call("list_assets", "call-1")), answer("Done."))
    rig = a_session(model, (LIST_ASSETS, FakeToolHandler.returning(LARGE_RESULT)))

    # When the model calls a tool with a large result
    await collect(rig.session.run_turn("Which assets are there?"))

    # Then the whole result reaches the model inline, as before
    assert json.loads(tool_message_for(model.history_of_call(2), "call-1").text) == LARGE_RESULT


async def test_two_calls_never_overwrite_each_others_files(tmp_path: Path) -> None:
    # Given one output directory shared by two runners, as after a restart job ids repeat
    outputs = outputs_in(tmp_path)

    # When each saves job j-1 of the same tool
    first = json.loads(outputs.render("j-1", "list_assets", {"n": 1}, to_file=True))
    second = json.loads(outputs.render("j-1", "list_assets", {"n": 2}, to_file=True))

    # Then they are two files, each with its own result
    assert first["saved_to_file"] != second["saved_to_file"]
    assert saved_result(first) == {"n": 1}
    assert saved_result(second) == {"n": 2}


# --- detached jobs -------------------------------------------------------------------------


async def test_a_large_result_of_an_async_job_reaches_its_notice_as_a_reference(
    tmp_path: Path,
) -> None:
    # Given an async search, still running after the turn, whose result is far over the limit
    search = FakeToolHandler.holding(LARGE_RESULT)
    model = ScriptedChatModel.replying(
        calling(tool_call("search_assets", "call-1")), answer("Started.")
    )
    rig = a_session(model, (SEARCH, search), outputs=outputs_in(tmp_path))
    await collect(rig.session.run_turn("Search for debris."))

    # When the job ends
    search.release()
    notice = await asyncio.wait_for(rig.runner.notices.get(), STEP_TIMEOUT_S)

    # Then its notice names the saved file instead of carrying the whole result
    assert len(notice.text) < LIMIT
    assert "saved_to_file" in notice.text


# --- scoping -------------------------------------------------------------------------------


def test_a_conversations_outputs_live_in_its_own_folder_under_the_root(tmp_path: Path) -> None:
    # Given the server's output root
    root = outputs_in(tmp_path)

    # When a conversation and one of its subagents get their outputs
    conversation = root.child("conv-1")
    subagent = conversation.child("sa-1")

    # Then each folder sits inside its parent's, with the same limit
    assert conversation.directory == tmp_path / "outputs" / "conv-1"
    assert subagent.directory == tmp_path / "outputs" / "conv-1" / "sa-1"
    assert subagent.max_inline_bytes == LIMIT


def test_a_conversation_id_cannot_climb_out_of_the_output_root(tmp_path: Path) -> None:
    # Given the server's output root
    root = outputs_in(tmp_path)

    # When a conversation id tries to name a folder above it
    escaped = root.child("../../etc")

    # Then the folder is still directly under the root
    assert escaped.directory is not None
    assert escaped.directory.parent == tmp_path / "outputs"


# --- the contract ------------------------------------------------------------------------


def offers_optional_to_file(contract: ToolContract) -> bool:
    """Whether the schema has an optional `output` object whose `to_file` is a boolean."""
    properties = contract.input_schema.get("properties")
    required = contract.input_schema.get("required", [])
    output = properties.get("output") if isinstance(properties, Mapping) else None
    to_file = output.get("properties", {}).get("to_file") if isinstance(output, Mapping) else None
    return (
        isinstance(to_file, Mapping)
        and to_file.get("type") == "boolean"
        and isinstance(required, list)
        and "output" not in required
    )


def test_every_proto_tool_offers_an_optional_output_to_file_argument() -> None:
    # Given the SurveyTools contracts built from the protos
    contracts = tool_contracts(survey_tools_pb2.DESCRIPTOR.services_by_name["SurveyTools"])

    # When their schemas are read
    offering = [offers_optional_to_file(contract) for contract in contracts]

    # Then every one offers output.to_file as an optional boolean
    assert offering and all(offering)
