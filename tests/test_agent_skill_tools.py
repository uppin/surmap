"""The `list_skills` / `load_skill` tools: bound like every other tool, and reachable
in a real turn of the agent server.

The tools are how a skill body enters a model's context: as an ordinary tool result the
model asked for, never as an addition to the shared system prompt.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages import ToolCall

from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import chat_pb2
from surmap.agent.runtime.jobs import Completed, Failed, JobRunner
from surmap.agent.server.app import AgentServerConfig, build_agent_description
from surmap.agent.skills import SkillCatalogue, skill_tools
from surmap.rpc.hosts.in_memory import InMemoryHost
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call, tool_message_for
from tests.agent_server_fakes import (
    CHAT_SERVICE,
    STEP_TIMEOUT_S,
    EmptyWorkspace,
    NoGlbs,
    turn_event,
)
from tests.fake_ollama import a_closed_ollama_url

MAP_SKILL_DESCRIPTION = (
    "How to use the map tools: place and move objects, navigate the camera, "
    "draw routes and load layers."
)


def a_catalogue_with_a_map_skill(tmp_path: Path) -> SkillCatalogue:
    directory = tmp_path / "builtin" / "using-the-map"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: using-the-map\ndescription: {MAP_SKILL_DESCRIPTION}\n---\n\n"
        "Place with add_map_object.\n",
        encoding="utf-8",
    )
    return SkillCatalogue(builtin_root=tmp_path / "builtin")


async def test_list_skills_reports_names_and_descriptions_only(tmp_path: Path) -> None:
    # Given the skill tools bound over a catalogue with one skill
    runner = JobRunner()
    tools = {
        tool.name: tool for tool in skill_tools(a_catalogue_with_a_map_skill(tmp_path), runner)
    }

    # When the model lists the skills
    outcome = await tools["list_skills"].run(tools["list_skills"].prepare({}))

    # Then it sees the name and the one-line description, and no body
    assert isinstance(outcome, Completed)
    assert outcome.result == {
        "skills": [{"name": "using-the-map", "description": MAP_SKILL_DESCRIPTION}]
    }


async def test_load_skill_returns_the_body_as_a_tool_result(tmp_path: Path) -> None:
    # Given the skill tools bound over a catalogue with one skill
    runner = JobRunner()
    tools = {
        tool.name: tool for tool in skill_tools(a_catalogue_with_a_map_skill(tmp_path), runner)
    }

    # When the model loads that skill
    prepared = tools["load_skill"].prepare({"name": "using-the-map"})
    outcome = await tools["load_skill"].run(prepared)

    # Then the result names the skill and carries its body
    assert isinstance(outcome, Completed)
    assert outcome.result == {"name": "using-the-map", "body": "Place with add_map_object.\n"}


async def test_loading_an_unknown_skill_fails_the_call_not_the_turn(tmp_path: Path) -> None:
    # Given the skill tools bound over a catalogue with one skill
    runner = JobRunner()
    tools = {
        tool.name: tool for tool in skill_tools(a_catalogue_with_a_map_skill(tmp_path), runner)
    }

    # When the model loads a skill that does not exist
    prepared = tools["load_skill"].prepare({"name": "flying"})
    outcome = await tools["load_skill"].run(prepared)

    # Then the call fails with the refusal, as any failing tool call does
    assert isinstance(outcome, Failed)
    assert "no skill called 'flying'" in outcome.error


def test_the_skill_tools_bind_under_the_names_the_model_calls() -> None:
    # Given the two skill tools
    tools = skill_tools(SkillCatalogue.shipped(), JobRunner())

    # When their model schemas are read
    schemas = [tool.model_schema() for tool in tools]

    # Then the model is offered exactly list_skills and load_skill
    assert [schema["function"]["name"] for schema in schemas] == ["list_skills", "load_skill"]  # type: ignore[index]


async def test_a_turn_can_list_and_load_the_shipped_map_skill(tmp_path: Path) -> None:
    # Given a server whose model lists the skills, loads the map skill, then answers
    model = ScriptedChatModel.replying(
        calling(tool_call("list_skills", "c1")),
        calling(
            ToolCall(
                name="load_skill",
                args={"name": "using-the-map"},
                id="c2",
                type="tool_call",
            )
        ),
        answer("I placed it."),
    )
    config = AgentServerConfig(model_id="ollama:scripted", model_factory=lambda _id: model)
    description = build_agent_description(
        config,
        workspace=EmptyWorkspace(),
        geometry=NoGlbs(),
        registry=ChatModelRegistry(environ={"SURMAP_OLLAMA_URL": a_closed_ollama_url()}),
    )
    server = InMemoryHost(description, None)

    # When a turn runs
    request = chat_pb2.StreamTurnRequest(
        conversation_id="conv-1", text="put the debris pile on the map"
    )
    stream = server.client(CHAT_SERVICE).server_stream("StreamTurn", request)

    async def read() -> list[object]:
        return [turn_event(message) async for message in stream]

    await asyncio.wait_for(read(), STEP_TIMEOUT_S)

    # Then the model was offered the skill tools alongside the map tools
    assert "list_skills" in model.bound_tool_names[0]
    assert "load_skill" in model.bound_tool_names[0]

    # And the listing it read names the shipped map skill
    history = model.history_of_call(2)
    listing = json.loads(str(tool_message_for(history, "c1").content))
    assert listing == {"skills": [{"name": "using-the-map", "description": MAP_SKILL_DESCRIPTION}]}

    # And the body it loaded teaches the map tools
    loaded = json.loads(str(tool_message_for(model.history_of_call(3), "c2").content))
    assert loaded["name"] == "using-the-map"
    assert "add_map_object" in loaded["body"]
