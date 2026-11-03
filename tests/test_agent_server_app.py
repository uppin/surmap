"""The agent process: its command line and environment, the models it builds, and the
`ServerDescription` that wires the hub, tools and routes together (mounted in memory).

`SurveyTools` handlers are injected proto fakes here, so n7's tools are not involved.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

import pytest
from langchain_core.messages import SystemMessage

from surmap.agent.__main__ import config_from_args
from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import chat_pb2
from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.server.app import (
    SYSTEM_PROMPT,
    AgentServerConfig,
    build_agent_description,
    default_model_factory,
)
from surmap.agent.services import Handler
from surmap.rpc.hosts.in_memory import InMemoryHost
from surmap.usage import BudgetExceeded, UsageLedger
from tests.agent_fakes import ScriptedChatModel, answer
from tests.agent_llm_fakes import FakeOllamaTags, RecordingMetaTransport
from tests.agent_server_fakes import (
    CHAT_SERVICE,
    JOB_CONTRACTS,
    STEP_TIMEOUT_S,
    SURVEY_CONTRACTS,
    SURVEY_TOOLS,
    EmptyWorkspace,
    NoGlbs,
    turn_event,
)

MUSE = "meta:muse-wonder-1.0"


async def a_run_echoing_its_id(request: pb.GetRunRequest, _ctx: object) -> pb.GetRunResponse:
    return pb.GetRunResponse(run=pb.RunInfo(run_id=request.run_id, dataset="euroc-v1-01-easy"))


def echoing_survey_handlers() -> Mapping[str, Handler]:
    return {contract.method: a_run_echoing_its_id for contract in SURVEY_CONTRACTS}


def a_server_answering_with(model: ScriptedChatModel) -> InMemoryHost[None]:
    config = AgentServerConfig(model_id="ollama:scripted", model_factory=lambda _id: model)
    description = build_agent_description(
        config,
        workspace=EmptyWorkspace(),
        geometry=NoGlbs(),
        registry=ChatModelRegistry(environ={}, ollama_transport=FakeOllamaTags("scripted")),
        survey_handlers=echoing_survey_handlers(),
    )
    return InMemoryHost(description, None)


async def one_turn(server: InMemoryHost[None], text: str) -> list[chat_pb2.TurnEvent]:
    request = chat_pb2.StreamTurnRequest(conversation_id="conv-1", text=text)
    stream = server.client(CHAT_SERVICE).server_stream("StreamTurn", request)

    async def read() -> list[chat_pb2.TurnEvent]:
        return [turn_event(message) async for message in stream]

    return await asyncio.wait_for(read(), STEP_TIMEOUT_S)


def a_keyed_registry(transport: RecordingMetaTransport) -> ChatModelRegistry:
    return ChatModelRegistry(
        environ={"MODEL_API_KEY": "sk-fixture-agent-key"},
        meta_transport=transport,
        ollama_transport=FakeOllamaTags(),
    )


# --- command line --------------------------------------------------------------------------


def test_with_no_flags_the_agent_serves_loopback_on_8780_for_the_vite_origin() -> None:
    # Given no flags and no environment
    argv: list[str] = []

    # When the command line is read
    config = config_from_args(argv, environ={})

    # Then it is the default config: 127.0.0.1:8780, Muse, CORS for localhost:5173
    assert config == AgentServerConfig(
        host="127.0.0.1",
        port=8780,
        model_id=MUSE,
        cors_origins=("http://localhost:5173",),
    )


def test_flags_set_the_port_model_history_and_fake_sam() -> None:
    # Given every flag
    argv = [
        "--port=9000",
        "--model=ollama:llama3.2",
        "--history-db=/data/demo-history.db",
        "--cache-dir=/data/demo-datasets",
        "--sam-fake",
    ]

    # When the command line is read
    config = config_from_args(argv, environ={})

    # Then the config carries each of them
    assert config == AgentServerConfig(
        port=9000,
        model_id="ollama:llama3.2",
        history_db=Path("/data/demo-history.db"),
        cache_dir=Path("/data/demo-datasets"),
        sam_fake=True,
    )


def test_cors_origins_come_from_the_environment_without_blank_entries() -> None:
    # Given two origins, comma-separated with a trailing comma
    environ = {"SURMAP_AGENT_CORS_ORIGINS": "http://localhost:5173, http://127.0.0.1:5173,"}

    # When the command line is read
    config = config_from_args([], environ=environ)

    # Then both origins are allowed, and nothing else
    assert config.cors_origins == ("http://localhost:5173", "http://127.0.0.1:5173")


# --- models --------------------------------------------------------------------------------


def test_a_muse_model_with_its_budget_spent_refuses_before_sending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given a Muse budget of zero calls
    monkeypatch.setenv("SURMAP_BUDGET_META_CALLS", "0")
    transport = RecordingMetaTransport.replying("text")
    model = default_model_factory(a_keyed_registry(transport), UsageLedger(tmp_path / "u.jsonl"))(
        MUSE
    )

    # When the agent calls it
    with pytest.raises(BudgetExceeded):
        model.invoke("what demos can you run?")

    # Then nothing was sent
    assert transport.calls == 0


def test_a_muse_model_records_its_usage_in_the_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given no Muse budget, and a ledger
    monkeypatch.delenv("SURMAP_BUDGET_META_CALLS", raising=False)
    ledger = UsageLedger(tmp_path / "u.jsonl")
    model = default_model_factory(
        a_keyed_registry(RecordingMetaTransport.replying("text")), ledger
    )(MUSE)

    # When the agent calls it once
    model.invoke("what demos can you run?")

    # Then the ledger counts that call
    assert ledger.calls("meta") == 1


# --- the wired server ----------------------------------------------------------------------


async def test_the_agent_s_model_reads_the_survey_system_prompt_first() -> None:
    # Given the server answering with a scripted model
    model = ScriptedChatModel.replying(answer("Hello"))
    server = a_server_answering_with(model)

    # When the user writes
    await one_turn(server, "hi")

    # Then the model's first message is the survey system prompt
    assert model.history_of_call(1)[0] == SystemMessage(content=SYSTEM_PROMPT)


async def test_the_agent_s_model_is_offered_every_survey_and_job_tool() -> None:
    # Given the server answering with a scripted model
    model = ScriptedChatModel.replying(answer("Hello"))
    server = a_server_answering_with(model)

    # When the user writes
    await one_turn(server, "hi")

    # Then the model was bound to all of them
    assert sorted(model.bound_tool_names[0]) == sorted(
        contract.name for contract in (*SURVEY_CONTRACTS, *JOB_CONTRACTS)
    )


async def test_the_ui_can_call_a_survey_tool_directly() -> None:
    # Given the server over handlers that echo a run id
    server = a_server_answering_with(ScriptedChatModel.replying(answer("Hello")))

    # When the UI calls SurveyTools.GetRun itself
    response = await server.client(SURVEY_TOOLS).unary("GetRun", pb.GetRunRequest(run_id="run-7"))

    # Then the handler answered it
    assert isinstance(response, pb.GetRunResponse)
    assert response.run.run_id == "run-7"


async def test_the_wired_server_answers_health() -> None:
    # Given the wired server
    server = a_server_answering_with(ScriptedChatModel.replying(answer("Hello")))

    # When a probe asks for /health
    response = await server.http("GET", "/health")

    # Then it is up
    assert response.status == 200
