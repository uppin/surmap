"""The agent server's subagents: the subagent tools are bound in every conversation, and the shipped
simulation skills delegate a scene build to a subagent and teach it the simulation tools."""

from __future__ import annotations

import asyncio

from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import chat_pb2
from surmap.agent.server.app import AgentServerConfig, build_agent_description
from surmap.agent.skills import SkillCatalogue
from surmap.rpc.hosts.in_memory import InMemoryHost
from tests.agent_fakes import (
    ScriptedChatModel,
    answer,
)
from tests.agent_server_fakes import (
    CHAT_SERVICE,
    STEP_TIMEOUT_S,
    EmptyWorkspace,
    NoGlbs,
)
from tests.fake_ollama import a_closed_ollama_url

# --- the agent server ----------------------------------------------------------------------


def test_the_shipped_skills_include_the_simulation_pair() -> None:
    # Given the shipped catalogue
    catalogue = SkillCatalogue.shipped()

    # When it is listed
    names = [skill.name for skill in catalogue.list_skills()]

    # Then the main agent's and the subagent's simulation skills are both there
    assert {"creating-a-simulation", "building-a-simulation-scene"} <= set(names)


def test_the_main_agent_s_simulation_skill_delegates_to_a_subagent_with_the_builder_skill() -> None:
    # Given the shipped main-agent simulation skill
    body = SkillCatalogue.shipped().load_skill("creating-a-simulation")

    # Then it tells the agent to start a subagent with the builder skill and to answer it
    assert "start_subagent" in body
    assert "building-a-simulation-scene" in body
    assert "message_subagent" in body


def test_the_builder_skill_teaches_the_simulation_tools_and_reporting_back() -> None:
    # Given the shipped subagent simulation skill
    body = SkillCatalogue.shipped().load_skill("building-a-simulation-scene")

    # Then it walks the scenario tools and says how to report to the main agent
    assert {"create_scenario", "get_scenario", "search_assets", "message_main_agent"} <= {
        word.strip("`.,()") for word in body.split()
    }


async def test_the_agent_server_offers_the_subagent_tools() -> None:
    # Given the agent server on a scripted model
    model = ScriptedChatModel.replying(answer("Hello."))
    config = AgentServerConfig(model_id="ollama:scripted", model_factory=lambda _id: model)
    description = build_agent_description(
        config,
        workspace=EmptyWorkspace(),
        geometry=NoGlbs(),
        registry=ChatModelRegistry(environ={"SURMAP_OLLAMA_URL": a_closed_ollama_url()}),
    )
    server = InMemoryHost(description, None)

    # When a turn runs
    request = chat_pb2.StreamTurnRequest(conversation_id="conv-1", text="Hi")
    stream = server.client(CHAT_SERVICE).server_stream("StreamTurn", request)

    async def read() -> list[object]:
        return [message async for message in stream]

    await asyncio.wait_for(read(), STEP_TIMEOUT_S)

    # Then the model may start and message subagents, but not message a main agent
    offered = set(model.bound_tool_names[0])
    assert {"start_subagent", "message_subagent"} <= offered
    assert "message_main_agent" not in offered
