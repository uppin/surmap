"""Test doubles for subagents: a real main `AgentSession` whose tools include the subagent tools,
over a separately scripted subagent model, and readers for what each conversation holds."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolCall,
)

from surmap.agent.runtime.graph import KIND_KEY
from surmap.agent.runtime.jobs import Job, JobRunner
from surmap.agent.runtime.session import AgentSession, InMemoryConversationStore
from surmap.agent.runtime.tools import BoundTool, bind_contract_tool, job_tools
from surmap.agent.skills import SkillValidationError
from surmap.agent.subagents import SubagentPool, SubagentSetup, subagent_tools
from tests.agent_fakes import (
    TIMEOUT_SCALE,
    FakeToolHandler,
    ScriptedChatModel,
    a_tool_contract,
    agent_job_contracts,
    answer,
    calling,
    resolve_locally,
    tool_call,
    tool_message_for,
)
from tests.agent_server_fakes import (
    STEP_TIMEOUT_S,
)

TASK = "Build a wildfire scene with three people fleeing"
SUBAGENT_PROMPT = "You are a subagent of the survey assistant."
SKILL_BODY = "Create the scenario with create_scenario, then light it with add_fire."
QUESTION = "Which side should the fire start on?"
ADD_FIRE = a_tool_contract(
    "add_fire", timeout_s=300, properties={"scenario_id": {"type": "string"}}
)


__all__ = [
    "ADD_FIRE",
    "QUESTION",
    "SKILL_BODY",
    "SUBAGENT_PROMPT",
    "TASK",
    "SubagentRig",
    "a_main_agent_with_subagents",
    "a_scene_builder_that_asks",
    "a_skill_loader",
    "result_of",
    "starting_the_scene_builder",
    "tagged",
]


def a_skill_loader(skills: Mapping[str, str]) -> Callable[[str], str]:
    def load(name: str) -> str:
        if name not in skills:
            raise SkillValidationError(f"no skill called {name!r}")
        return skills[name]

    return load


@dataclass
class SubagentRig:
    """A real main session whose tools include the subagent tools, over a scripted subagent."""

    main: AgentSession
    main_model: ScriptedChatModel
    main_runner: JobRunner
    main_store: InMemoryConversationStore
    subagent_model: ScriptedChatModel
    add_fire: FakeToolHandler
    turns: list[asyncio.Task[object]] = field(default_factory=list)

    @property
    def main_history(self) -> list[BaseMessage]:
        return self.main_store.history(self.main.conversation_id)

    async def subagent_job(self, job_id: str) -> Job:
        """The subagent turn's job once it has ended."""
        waited = await self.main_runner.wait([job_id], "all", STEP_TIMEOUT_S)
        assert not waited.timed_out, f"{job_id} is still running"
        return waited.jobs[0]


def a_main_agent_with_subagents(
    main_model: ScriptedChatModel,
    subagent_model: ScriptedChatModel,
    *,
    add_fire: FakeToolHandler | None = None,
    skills: Mapping[str, str] | None = None,
    max_running: int = 3,
) -> SubagentRig:
    fire = add_fire if add_fire is not None else FakeToolHandler.returning({"fire_id": "fire-1"})

    def tools(runner: JobRunner) -> Sequence[BoundTool]:
        return (
            bind_contract_tool(ADD_FIRE, fire, runner, resolve=resolve_locally),
            *job_tools(runner, agent_job_contracts(), resolve=resolve_locally),
        )

    runner = JobRunner(timeout_scale=TIMEOUT_SCALE)
    store = InMemoryConversationStore()
    pool = SubagentPool(
        conversation_id="conv-1",
        runner=runner,
        model=lambda: subagent_model,
        tools=tools,
        setup=SubagentSetup(
            system_prompt=SUBAGENT_PROMPT,
            load_skill=a_skill_loader(skills or {"building-a-simulation-scene": SKILL_BODY}),
            max_running=max_running,
        ),
    )
    main = AgentSession(
        conversation_id="conv-1",
        model=main_model,
        tools=[*tools(runner), *subagent_tools(pool)],
        runner=runner,
        store=store,
    )
    return SubagentRig(
        main=main,
        main_model=main_model,
        main_runner=runner,
        main_store=store,
        subagent_model=subagent_model,
        add_fire=fire,
    )


def starting_the_scene_builder(call_id: str = "s1") -> AIMessage:
    # Built by hand: the tool's `name` argument would collide with `tool_call`'s own.
    arguments = {"task": TASK, "name": "scene-builder", "skill": "building-a-simulation-scene"}
    return calling(ToolCall(name="start_subagent", args=arguments, id=call_id, type="tool_call"))


def result_of(history: Sequence[BaseMessage], call_id: str) -> dict[str, object]:
    message = tool_message_for(history, call_id)
    assert message.status == "success", f"{call_id} failed: {message.content}"
    loaded = json.loads(str(message.content))
    assert isinstance(loaded, dict)
    return loaded


def tagged(history: Sequence[BaseMessage], kind: str) -> list[str]:
    """The text of every human message in `history` tagged with `kind`."""
    return [
        m.text
        for m in history
        if isinstance(m, HumanMessage) and m.additional_kwargs.get(KIND_KEY) == kind
    ]


def a_scene_builder_that_asks() -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(tool_call("message_main_agent", "m1", text=QUESTION)),
        answer("Waiting for the answer."),
    )
