"""Subagents: a conversation hands one task to an agent of its own, steers it, and hears back.

A long piece of work — a simulation scene is dozens of small edits — would otherwise fill the
conversation's context with every call it made. A subagent does it in a context of its own: an
`AgentSession` with its own `JobRunner` and history, on the conversation's current model, bound
to the conversation's tools without the subagent tools (subagents do not nest) plus
`message_main_agent`. Its system prompt is `SubagentSetup.system_prompt` followed, when the start
names one, by a skill's body. The conversation sees only what the subagent chooses to say — its
messages and its final answer — never its tool calls.

Three tools:

- `start_subagent` starts one and returns its id (`sa-1`, `sa-2`, …) and the job its turn runs
  as. The turn is an ASYNC job of the conversation's runner, named `subagent:<id>`, so its end is
  a job notice and `wait_for_jobs`, `cancel_job`, Stop and the jobs panel cover it like any job;
  its result is the subagent's final answer. At most `SubagentSetup.max_running` run at once.
- `message_subagent` steers a running subagent (`AgentSession.steer`: its blocking calls detach,
  the text is the next thing it reads) or, when its turn has ended, starts a follow-up turn on the
  history it kept, as a new job.
- `message_main_agent`, the subagent's own, queues a `SubagentNotice` on the conversation's notice
  queue: the main agent reads it before its next model call during a turn, and while the
  conversation idles it opens a turn (`AgentSession.idle_events`).

A subagent's own detached jobs that end after its turn are read at its next turn.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from surmap.agent.contracts import (
    ExecutionMode,
    ExecutionPolicy,
    OnTimeout,
    ToolContract,
    tool_input_schema,
)
from surmap.agent.runtime.events import FinishReason, TurnError, TurnEvent, TurnFinished
from surmap.agent.runtime.graph import SUBAGENT_KIND, TurnCaps
from surmap.agent.runtime.jobs import Detached, JobRunner, SubagentNotice
from surmap.agent.runtime.session import AgentSession, InMemoryConversationStore
from surmap.agent.runtime.tools import BoundTool, bind_contract_tool

__all__ = [
    "DEFAULT_MAX_RUNNING",
    "MESSAGE_MAIN_AGENT",
    "SUBAGENT_KIND",
    "SUBAGENT_TOOL_NAMES",
    "SubagentPool",
    "SubagentSetup",
    "subagent_contracts",
    "subagent_tools",
]

SUBAGENT_TOOL_NAMES = frozenset({"start_subagent", "message_subagent"})
"""The main agent's subagent tools; a subagent is never bound to them."""
MESSAGE_MAIN_AGENT = "message_main_agent"
"""The tool a subagent messages the conversation that started it with."""
DEFAULT_MAX_RUNNING = 3
"""How many subagents of one conversation may run at once."""

_SERVICE = "surmap.agent.subagents"
_DEFAULT_NAME = "subagent"
_DEFAULT_EXECUTION = ExecutionPolicy(
    mode=ExecutionMode.SYNC, timeout_s=10, on_timeout=OnTimeout.FAIL
)
_TURN_EXECUTION = ExecutionPolicy(mode=ExecutionMode.ASYNC, timeout_s=0, on_timeout=OnTimeout.FAIL)
"""A subagent's turn: a job handle at once; the turn reports when it ends."""

ModelSource = Callable[[], BaseChatModel]
"""The model a subagent's turn runs on: the conversation's, as it is when the turn starts."""
ToolSource = Callable[[JobRunner], Sequence[BoundTool]]
"""The conversation's tools over a runner, as `surmap.agent.server.hub.ToolFactory` builds them."""


@dataclass(frozen=True)
class SubagentSetup:
    """What every subagent of a server starts from."""

    system_prompt: str
    """Who a subagent is and how it reports; a named skill's body follows it."""
    load_skill: Callable[[str], str]
    """A skill's body by name (`SkillCatalogue.load_skill`); raises `ValueError` for none."""
    max_running: int = DEFAULT_MAX_RUNNING


@dataclass
class _Subagent:
    subagent_id: str
    name: str
    session: AgentSession
    job_id: str = ""
    """The job of its latest turn."""


class SubagentPool:
    """The subagents of one conversation, started on and reporting to its runner."""

    def __init__(
        self,
        *,
        conversation_id: str,
        runner: JobRunner,
        model: ModelSource,
        tools: ToolSource,
        setup: SubagentSetup,
        caps: TurnCaps | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.runner = runner
        self.model = model
        self.tools = tools
        self.setup = setup
        self.caps = caps
        self._subagents: dict[str, _Subagent] = {}

    async def start(self, task: str, *, name: str, skill: str | None) -> dict[str, object]:
        """Start a subagent on `task` with `skill`'s instructions; its id and its turn's job.

        Raises `ValueError` past the running cap or for a skill `load_skill` refuses.
        """
        self._require_room()
        prompt = self.setup.system_prompt
        if skill is not None:
            prompt = f"{prompt}\n\n# Your skill: {skill}\n\n{self.setup.load_skill(skill)}"
        subagent_id = f"sa-{len(self._subagents) + 1}"
        runner = JobRunner(
            timeout_scale=self.runner.timeout_scale,
            clock=self.runner.clock,
            outputs=self.runner.outputs.child(subagent_id),
        )
        tools = [tool for tool in self.tools(runner) if tool.name not in SUBAGENT_TOOL_NAMES]
        tools.append(self._message_main_agent(subagent_id, name, runner))
        session = AgentSession(
            conversation_id=f"{self.conversation_id}/{subagent_id}",
            model=self.model(),
            tools=tools,
            runner=runner,
            store=InMemoryConversationStore(),
            caps=self.caps,
            system_prompt=prompt,
        )
        subagent = _Subagent(subagent_id=subagent_id, name=name, session=session)
        self._subagents[subagent_id] = subagent
        job_id = await self._run_turn(subagent, task)
        return {"subagent_id": subagent_id, "name": name, "job_id": job_id}

    async def message(self, subagent_id: str, text: str) -> dict[str, object]:
        """Steer the subagent while it runs, or start its follow-up turn once it has ended.

        Raises `ValueError` for an id this conversation never started, or past the running cap
        when a follow-up would start.
        """
        subagent = self._subagents.get(subagent_id)
        if subagent is None:
            raise ValueError(f"no subagent {subagent_id}; start_subagent returns the id")
        if subagent.session.running:
            subagent.session.steer(text)
            return {"subagent_id": subagent_id, "delivered": "STEER", "job_id": subagent.job_id}
        self._require_room()
        subagent.session.model = self.model()
        job_id = await self._run_turn(subagent, text)
        return {"subagent_id": subagent_id, "delivered": "NEW_TURN", "job_id": job_id}

    def _require_room(self) -> None:
        running = sum(subagent.session.running for subagent in self._subagents.values())
        if running >= self.setup.max_running:
            raise ValueError(
                f"at most {self.setup.max_running} subagents run at once; wait for one to "
                "finish or cancel_job its job"
            )

    async def _run_turn(self, subagent: _Subagent, text: str) -> str:
        """Start the subagent's turn on `text` as an ASYNC job of the conversation; its id."""
        # Starting the turn here, before the job exists, makes the session running at once, so
        # a message arriving before the job's first step steers this turn instead of racing it.
        events = subagent.session.run_turn(text)
        outcome = await self.runner.call(
            _turn_contract(subagent.subagent_id),
            {},
            lambda _arguments: _follow(subagent, events),
            policy=_TURN_EXECUTION,
        )
        if not isinstance(outcome, Detached):
            raise RuntimeError(f"the turn of {subagent.subagent_id} did not start as a job")
        subagent.job_id = outcome.job.job_id
        return subagent.job_id

    def _message_main_agent(self, subagent_id: str, name: str, runner: JobRunner) -> BoundTool:
        async def send(arguments: Mapping[str, object]) -> Mapping[str, object]:
            text = _string(arguments, "text")
            self.runner.notices.put_nowait(
                SubagentNotice(
                    subagent_id=subagent_id,
                    name=name,
                    message=text,
                    text=_notice_text(subagent_id, name, text),
                )
            )
            return {"delivered": True}

        contract = {contract.name: contract for contract in subagent_contracts()}
        return bind_contract_tool(contract[MESSAGE_MAIN_AGENT], send, runner)


def subagent_tools(pool: SubagentPool) -> tuple[BoundTool, BoundTool]:
    """`start_subagent` and `message_subagent` over `pool`, run by its conversation's runner."""

    async def start(arguments: Mapping[str, object]) -> Mapping[str, object]:
        skill = arguments.get("skill")
        if skill is not None and not isinstance(skill, str):
            raise ValueError("skill must be a string")
        name = arguments.get("name", _DEFAULT_NAME)
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        return await pool.start(_string(arguments, "task"), name=name, skill=skill or None)

    async def message(arguments: Mapping[str, object]) -> Mapping[str, object]:
        return await pool.message(_string(arguments, "subagent_id"), _string(arguments, "text"))

    contracts = {contract.name: contract for contract in subagent_contracts()}
    return (
        bind_contract_tool(contracts["start_subagent"], start, pool.runner),
        bind_contract_tool(contracts["message_subagent"], message, pool.runner),
    )


def subagent_contracts() -> tuple[ToolContract, ToolContract, ToolContract]:
    """`start_subagent`, `message_subagent` and the subagent's own `message_main_agent`."""
    return (
        ToolContract(
            name="start_subagent",
            service=_SERVICE,
            method="StartSubagent",
            description=(
                "Hands one task to a subagent: an agent with your tools and a context of its "
                "own, so its many tool calls stay out of this conversation. It starts at once "
                "and runs as a job; its final answer arrives as that job's notice, and anything "
                "it asks you arrives as a subagent message. Give it the whole brief in task — it "
                "sees nothing of this conversation."
            ),
            input_schema=tool_input_schema(
                {
                    "task": {
                        "type": "string",
                        "description": (
                            "Everything the subagent needs to do the work: the goal, every "
                            "requirement the person gave, and what to report back."
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "A short label shown with its messages, e.g. scene-builder.",
                    },
                    "skill": {
                        "type": "string",
                        "description": (
                            "A skill, by the name list_skills reports, whose instructions the "
                            "subagent follows."
                        ),
                    },
                },
                required=("task",),
            ),
            default_execution=_DEFAULT_EXECUTION,
        ),
        ToolContract(
            name="message_subagent",
            service=_SERVICE,
            method="MessageSubagent",
            description=(
                "Sends a subagent a message: guidance it acts on next while it runs, or a new "
                "request — an answer to its question, a change — that starts another turn on "
                "everything it has done so far once it has finished."
            ),
            input_schema=tool_input_schema(
                {
                    "subagent_id": {
                        "type": "string",
                        "description": "The subagent, as start_subagent returned it, e.g. sa-1.",
                    },
                    "text": {"type": "string", "description": "The message."},
                },
                required=("subagent_id", "text"),
            ),
            default_execution=_DEFAULT_EXECUTION,
        ),
        ToolContract(
            name=MESSAGE_MAIN_AGENT,
            service=_SERVICE,
            method="MessageMainAgent",
            description=(
                "Sends the main agent, who gave you your task, a message while you keep "
                "working: a question only it or the person can answer, or a decision it must "
                "know about now. Your final answer reaches it anyway; do not report progress."
            ),
            input_schema=tool_input_schema(
                {"text": {"type": "string", "description": "The message."}},
                required=("text",),
            ),
            default_execution=_DEFAULT_EXECUTION,
        ),
    )


def _turn_contract(subagent_id: str) -> ToolContract:
    """What the conversation's runner records a subagent's turn as: job tool `subagent:<id>`."""
    return ToolContract(
        name=f"subagent:{subagent_id}",
        service=_SERVICE,
        method="RunSubagentTurn",
        description=f"One turn of subagent {subagent_id}.",
        input_schema=tool_input_schema({}),
        default_execution=_TURN_EXECUTION,
    )


async def _follow(subagent: _Subagent, events: AsyncIterator[TurnEvent]) -> Mapping[str, object]:
    """Wait out the subagent's turn; its final answer, or a failure when the turn errored.

    Cancelling the job cancels the turn and every job the subagent is running.
    """
    reason: FinishReason = "stop"
    error = ""
    try:
        async for event in events:
            if isinstance(event, TurnError):
                error = event.message
            elif isinstance(event, TurnFinished):
                reason = event.reason
    except asyncio.CancelledError:
        await subagent.session.cancel()
        raise
    if reason == "error":
        raise RuntimeError(f"subagent {subagent.subagent_id} failed: {error}")
    return {
        "subagent_id": subagent.subagent_id,
        "name": subagent.name,
        "finish_reason": reason,
        "reply": _last_answer(subagent.session),
    }


def _last_answer(session: AgentSession) -> str:
    history = session.store.history(session.conversation_id)
    answers = [message.text for message in history if isinstance(message, AIMessage)]
    return answers[-1] if answers else ""


def _notice_text(subagent_id: str, name: str, text: str) -> str:
    return (
        f"Subagent {subagent_id} ({name}) says: {text}\n"
        f"It keeps working. When it asks you something, answer with message_subagent "
        f"(subagent_id {subagent_id})."
    )


def _string(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value
