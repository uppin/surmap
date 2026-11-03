"""The agent process: its command line and environment, the models it builds, and the
`ServerDescription` that wires the hub, tools and routes together (mounted in memory).

`SurveyTools` handlers are injected proto fakes here, so n7's tools are not involved.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path

import pytest
from langchain_core.messages import SystemMessage

from surmap.agent import __main__ as agent_main
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
from tests import fake_meta, fake_ollama
from tests.agent_fakes import ScriptedChatModel, answer
from tests.agent_server_fakes import (
    CHAT_SERVICE,
    JOB_CONTRACTS,
    MAP_CONTRACTS,
    STEP_TIMEOUT_S,
    SURVEY_CONTRACTS,
    SURVEY_TOOLS,
    EmptyWorkspace,
    NoGlbs,
    turn_event,
)
from tests.agent_tool_fakes import a_tool_rig
from tests.fake_fireworks import (
    FAKE_FIREWORKS_KEY,
    FAKE_FIREWORKS_MODEL,
    FakeFireworksScript,
    answering,
    calling,
    serving,
)
from tests.fake_meta import FAKE_META_KEY, FakeMetaScript
from tests.fake_ollama import FakeOllamaScript, a_closed_ollama_url

MUSE = "meta:muse-wonder-1.0"
FIREWORKS = f"fireworks:{FAKE_FIREWORKS_MODEL}"
LLAMA = "ollama:llama3.2:3b"


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
        registry=ChatModelRegistry(environ={"SURMAP_OLLAMA_URL": a_closed_ollama_url()}),
        survey_handlers=echoing_survey_handlers(),
    )
    return InMemoryHost(description, None)


async def one_turn(server: InMemoryHost[None], text: str) -> list[chat_pb2.TurnEvent]:
    request = chat_pb2.StreamTurnRequest(conversation_id="conv-1", text=text)
    stream = server.client(CHAT_SERVICE).server_stream("StreamTurn", request)

    async def read() -> list[chat_pb2.TurnEvent]:
        return [turn_event(message) async for message in stream]

    return await asyncio.wait_for(read(), STEP_TIMEOUT_S)


def a_keyed_registry(meta_base_url: str) -> ChatModelRegistry:
    return ChatModelRegistry(
        environ={"MODEL_API_KEY": FAKE_META_KEY, "SURMAP_OLLAMA_URL": a_closed_ollama_url()},
        meta_base_url=meta_base_url,
    )


def a_fireworks_registry(base_url: str) -> ChatModelRegistry:
    return ChatModelRegistry(
        environ={
            "FIREWORKS_API_KEY": FAKE_FIREWORKS_KEY,
            "SURMAP_FIREWORKS_URL": base_url,
            "SURMAP_OLLAMA_URL": a_closed_ollama_url(),
        },
    )


def an_ollama_registry(base_url: str) -> ChatModelRegistry:
    return ChatModelRegistry(environ={"SURMAP_OLLAMA_URL": base_url})


async def a_whole_turn(
    tmp_path: Path, model_id: str, registry: ChatModelRegistry
) -> list[chat_pb2.TurnEvent]:
    """One user turn on `model_id` from `registry`, over the tiny scene's workspace."""
    with a_tool_rig(tmp_path) as rig:
        description = build_agent_description(
            AgentServerConfig(model_id=model_id),
            workspace=rig.workspace,
            geometry=rig.workspace.geometry,
            registry=registry,
        )
        return await one_turn(InMemoryHost(description, None), "what demos can you run?")


def the_tool_call_then_stop(events: list[chat_pb2.TurnEvent]) -> list[str]:
    """The turn's event kinds without text deltas; asserts it stopped normally."""
    assert events[-1].turn_finished.reason == chat_pb2.TurnFinished.STOP
    return [e.WhichOneof("event") for e in events if e.WhichOneof("event") != "text_delta"]


def without_env(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Unset `names` so that whatever sets them later is undone after the test."""
    for name in names:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


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


def test_a_fireworks_model_id_is_taken_whole_from_the_command_line() -> None:
    # Given a Fireworks model id, slashes and all
    argv = [f"--model={FIREWORKS}"]

    # When the command line is read
    config = config_from_args(argv, environ={})

    # Then the config's default model is that id
    assert config.model_id == FIREWORKS


def test_cors_origins_come_from_the_environment_without_blank_entries() -> None:
    # Given two origins, comma-separated with a trailing comma
    environ = {"SURMAP_AGENT_CORS_ORIGINS": "http://localhost:5173, http://127.0.0.1:5173,"}

    # When the command line is read
    config = config_from_args([], environ=environ)

    # Then both origins are allowed, and nothing else
    assert config.cors_origins == ("http://localhost:5173", "http://127.0.0.1:5173")


def test_ctrl_c_stops_the_agent_with_a_line_and_no_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given a server that is interrupted by Ctrl-C while serving
    async def interrupted(config: AgentServerConfig) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(agent_main, "serve", interrupted)

    # When the agent runs
    agent_main.main(["--sam-fake"])

    # Then it returns normally and says it stopped
    assert "survey agent stopped" in capsys.readouterr().out


# --- the project .env ----------------------------------------------------------------------

DOTENV_KEYS = ("MODEL_API_KEY", "FIREWORKS_API_KEY", "SURMAP_FIREWORKS_MODELS")


def a_project_env(directory: Path, **entries: str) -> None:
    (directory / ".env").write_text("".join(f"{k}={v}\n" for k, v in entries.items()))


def models_listed_by_main(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], dict[str, str]]:
    """Run `main` with `serve` replaced: the model ids the process would list, and its keys."""
    seen: list[str] = []
    keys: dict[str, str] = {}

    monkeypatch.setenv("SURMAP_OLLAMA_URL", a_closed_ollama_url())

    async def listing(config: AgentServerConfig) -> None:
        registry = ChatModelRegistry()
        seen.extend(info.id for info in registry.available())
        keys.update({name: os.environ.get(name, "") for name in DOTENV_KEYS})

    monkeypatch.setattr(agent_main, "serve", listing)
    agent_main.main(["--sam-fake"])
    return seen, keys


def test_main_reads_muse_and_fireworks_keys_from_the_project_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given no keys in the shell and a project .env holding both, naming one Fireworks model
    without_env(monkeypatch, *DOTENV_KEYS)
    a_project_env(
        tmp_path,
        MODEL_API_KEY="sk-dotenv-muse",
        FIREWORKS_API_KEY=FAKE_FIREWORKS_KEY,
        SURMAP_FIREWORKS_MODELS=FAKE_FIREWORKS_MODEL,
    )
    monkeypatch.chdir(tmp_path)

    # When the agent process starts there
    listed, _keys = models_listed_by_main(monkeypatch)

    # Then Muse and the Fireworks model are offered
    assert listed == [MUSE, FIREWORKS]


def test_a_shell_export_wins_over_the_project_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given FIREWORKS_API_KEY exported in the shell and a different one in the project .env
    without_env(monkeypatch, *DOTENV_KEYS)
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-from-the-shell")
    a_project_env(
        tmp_path, FIREWORKS_API_KEY=FAKE_FIREWORKS_KEY, SURMAP_FIREWORKS_MODELS=FAKE_FIREWORKS_MODEL
    )
    monkeypatch.chdir(tmp_path)

    # When the agent process starts there
    _listed, keys = models_listed_by_main(monkeypatch)

    # Then the shell's key is the one in force
    assert keys["FIREWORKS_API_KEY"] == "fw-from-the-shell"


# --- models --------------------------------------------------------------------------------


def test_a_muse_model_with_its_budget_spent_refuses_before_sending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given a Muse budget of zero calls
    monkeypatch.setenv("SURMAP_BUDGET_META_CALLS", "0")
    script = FakeMetaScript(rounds=[fake_meta.answering("ok")])
    with fake_meta.serving(script) as base:
        model = default_model_factory(a_keyed_registry(base), UsageLedger(tmp_path / "u.jsonl"))(
            MUSE
        )

        # When the agent calls it
        with pytest.raises(BudgetExceeded):
            model.invoke("what demos can you run?")

    # Then nothing was sent
    assert script.requests == []


def test_a_muse_model_records_its_usage_in_the_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given no Muse budget, and a ledger
    monkeypatch.delenv("SURMAP_BUDGET_META_CALLS", raising=False)
    ledger = UsageLedger(tmp_path / "u.jsonl")
    with fake_meta.serving(FakeMetaScript(rounds=[fake_meta.answering("ok")])) as base:
        model = default_model_factory(a_keyed_registry(base), ledger)(MUSE)

        # When the agent calls it once
        model.invoke("what demos can you run?")

    # Then the ledger counts that call
    assert ledger.calls("meta") == 1


def test_a_fireworks_model_with_its_budget_spent_refuses_before_sending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given a Fireworks budget of zero calls
    monkeypatch.setenv("SURMAP_BUDGET_FIREWORKS_CALLS", "0")
    script = FakeFireworksScript(rounds=[answering("ok")])
    with serving(script) as base:
        model = default_model_factory(
            a_fireworks_registry(base), UsageLedger(tmp_path / "u.jsonl")
        )(FIREWORKS)

        # When the agent calls it
        with pytest.raises(BudgetExceeded):
            model.invoke("what demos can you run?")

    # Then nothing was sent
    assert script.chat_requests == []


def test_a_fireworks_model_records_its_usage_in_the_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given no Fireworks budget, and a ledger
    monkeypatch.delenv("SURMAP_BUDGET_FIREWORKS_CALLS", raising=False)
    ledger = UsageLedger(tmp_path / "u.jsonl")
    with serving(FakeFireworksScript(rounds=[answering("ok")])) as base:
        model = default_model_factory(a_fireworks_registry(base), ledger)(FIREWORKS)

        # When the agent calls it once
        model.invoke("what demos can you run?")

    # Then the ledger counts that call
    assert ledger.calls("fireworks") == 1


async def test_a_whole_turn_on_a_fireworks_model_lists_the_demos_and_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given the agent over the tiny scene, defaulting to a Fireworks model on the fake provider,
    # scripted to call list_demos and then answer
    monkeypatch.delenv("SURMAP_BUDGET_FIREWORKS_CALLS", raising=False)
    monkeypatch.setenv("SURMAP_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    script = FakeFireworksScript(
        rounds=[calling("list_demos", "call-1"), answering("The tiny scene is ready.")]
    )
    with serving(script) as base, a_tool_rig(tmp_path) as rig:
        description = build_agent_description(
            AgentServerConfig(model_id=FIREWORKS),
            workspace=rig.workspace,
            geometry=rig.workspace.geometry,
            registry=a_fireworks_registry(base),
        )

        # When the user writes
        events = await one_turn(InMemoryHost(description, None), "what demos can you run?")

    # Then list_demos ran as a tool call and the turn stopped normally
    assert [e.WhichOneof("event") for e in events if e.WhichOneof("event") != "text_delta"] == [
        "user_message",
        "tool_call_started",
        "tool_call_finished",
        "turn_finished",
    ]
    assert events[-1].turn_finished.reason == chat_pb2.TurnFinished.STOP
    assert len(script.chat_requests) == 2


async def test_a_whole_turn_on_a_muse_model_lists_the_demos_and_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given the agent defaulting to Muse on the fake Meta server, scripted to call list_demos and
    # then answer
    monkeypatch.delenv("SURMAP_BUDGET_META_CALLS", raising=False)
    monkeypatch.setenv("SURMAP_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    script = FakeMetaScript(
        rounds=[fake_meta.calling("list_demos", "call-1"), fake_meta.answering("Ready.")]
    )
    with fake_meta.serving(script) as base:
        # When the user writes
        events = await a_whole_turn(tmp_path, MUSE, a_keyed_registry(base))

    # Then list_demos ran as a tool call, its result went back under call-1, and the turn stopped
    assert the_tool_call_then_stop(events) == [
        "user_message",
        "tool_call_started",
        "tool_call_finished",
        "turn_finished",
    ]
    answered = script.responses_requests[1].body["input"]
    assert isinstance(answered, list)
    assert [i["call_id"] for i in answered if i["type"] == "function_call_output"] == ["call-1"]


async def test_a_whole_turn_on_an_ollama_model_lists_the_demos_and_stops(tmp_path: Path) -> None:
    # Given the agent defaulting to an Ollama model on the fake Ollama server, scripted to call
    # list_demos and then answer
    script = FakeOllamaScript(
        rounds=[fake_ollama.calling("list_demos"), fake_ollama.answering("Ready.")]
    )
    with fake_ollama.serving(script) as base:
        # When the user writes
        events = await a_whole_turn(tmp_path, LLAMA, an_ollama_registry(base))

    # Then list_demos ran as a tool call and the turn stopped normally after two chat requests
    assert the_tool_call_then_stop(events) == [
        "user_message",
        "tool_call_started",
        "tool_call_finished",
        "turn_finished",
    ]
    assert len(script.chat_requests) == 2


# --- the wired server ----------------------------------------------------------------------


async def test_the_agent_s_model_reads_the_survey_system_prompt_first() -> None:
    # Given the server answering with a scripted model
    model = ScriptedChatModel.replying(answer("Hello"))
    server = a_server_answering_with(model)

    # When the user writes
    await one_turn(server, "hi")

    # Then the model's first message is the survey system prompt
    assert model.history_of_call(1)[0] == SystemMessage(content=SYSTEM_PROMPT)


async def test_the_agent_s_model_is_offered_every_survey_map_and_job_tool() -> None:
    # Given the server answering with a scripted model
    model = ScriptedChatModel.replying(answer("Hello"))
    server = a_server_answering_with(model)

    # When the user writes
    await one_turn(server, "hi")

    # Then the model was bound to all of them
    assert sorted(model.bound_tool_names[0]) == sorted(
        contract.name for contract in (*SURVEY_CONTRACTS, *MAP_CONTRACTS, *JOB_CONTRACTS)
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
