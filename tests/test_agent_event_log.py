"""The agent's event log: one greppable `event=… key=value` line per thing that happened.

In production these lines are what `modal app logs surmap-agent | grep event=…` finds: a turn
that ends with no reply shows `text_chars=0`, a slow tool its `duration_ms`, a refused caller
its surface. Captured here with `caplog` on the `surmap.agent.events` logger.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from connectrpc.errors import ConnectError

from surmap.agent.event_log import EVENT_LOGGER, logfmt
from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import chat_pb2
from surmap.agent.server.app import AgentServerConfig, build_agent_description
from surmap.agent.tools.station import StubStationControl
from surmap.rpc.hosts.in_memory import InMemoryHost
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call
from tests.agent_server_fakes import CHAT_SERVICE, STEP_TIMEOUT_S, EmptyWorkspace, NoGlbs
from tests.agent_station_fakes import FakeClock
from tests.fake_ollama import a_closed_ollama_url

CODE = "correct-horse-battery-staple"


class _Lines:
    """The event lines logged during a test, as they will read in production."""

    def __init__(self, caplog: pytest.LogCaptureFixture) -> None:
        self._caplog = caplog

    def named(self, event: str) -> list[str]:
        return [
            record.getMessage()
            for record in self._caplog.records
            if record.name == EVENT_LOGGER and record.getMessage().startswith(f"event={event} ")
        ]

    def all(self) -> str:
        return "\n".join(record.getMessage() for record in self._caplog.records)


@pytest.fixture
def lines(caplog: pytest.LogCaptureFixture) -> _Lines:
    caplog.set_level(logging.INFO, logger=EVENT_LOGGER)
    return _Lines(caplog)


def an_agent(model: ScriptedChatModel, *, access_code: str | None = None) -> InMemoryHost[None]:
    config = AgentServerConfig(
        model_id="ollama:scripted", model_factory=lambda _id: model, access_code=access_code
    )
    description = build_agent_description(
        config,
        workspace=EmptyWorkspace(),
        geometry=NoGlbs(),
        registry=ChatModelRegistry(environ={"SURMAP_OLLAMA_URL": a_closed_ollama_url()}),
    )
    return InMemoryHost(description, None)


async def one_turn(agent: InMemoryHost[None], text: str) -> None:
    request = chat_pb2.StreamTurnRequest(conversation_id="conv-1", text=text)

    async def read() -> None:
        async for _event in agent.client(CHAT_SERVICE).server_stream("StreamTurn", request):
            pass

    await asyncio.wait_for(read(), STEP_TIMEOUT_S)


def test_a_line_is_the_event_then_its_fields_quoted_only_when_needed() -> None:
    # Given an event with plain, spaced and quoted values
    line = logfmt("turn_error", conversation="conv-1", error='model said "no" twice', tools=0)

    # Then it reads as one greppable key=value line
    assert line == 'event=turn_error conversation=conv-1 error="model said \\"no\\" twice" tools=0'


async def test_a_turn_logs_its_start_and_its_end_with_the_reply_length(lines: _Lines) -> None:
    # Given an agent whose model answers "Hi there!"
    agent = an_agent(ScriptedChatModel.replying(answer("Hi there!")))

    # When a person says hi
    await one_turn(agent, "hi")

    # Then the turn's start names the model, and its end the reason, reply length and tools
    (started,) = lines.named("turn_started")
    assert "conversation=conv-1" in started and "model=ollama:scripted" in started
    assert "trigger=user" in started
    (finished,) = lines.named("turn_finished")
    assert "reason=stop" in finished and "text_chars=9" in finished and "tools=0" in finished
    assert "duration_ms=" in finished


async def test_a_turn_with_no_reply_text_shows_as_zero_characters(lines: _Lines) -> None:
    # Given an agent whose model ends the turn saying nothing
    agent = an_agent(ScriptedChatModel.replying(answer("")))

    # When a person asks something
    await one_turn(agent, "hi")

    # Then the end of the turn says no text reached the chat
    (finished,) = lines.named("turn_finished")
    assert "text_chars=0" in finished


async def test_each_tool_call_logs_its_tool_status_and_duration(lines: _Lines) -> None:
    # Given an agent whose model lists the demos, then answers
    agent = an_agent(
        ScriptedChatModel.replying(calling(tool_call("list_demos", "call-1")), answer("Two demos."))
    )

    # When a person asks for the demos
    await one_turn(agent, "what demos?")

    # Then the call's start and end are logged, and the turn counts one tool call
    (started,) = lines.named("tool_started")
    assert "tool=list_demos" in started and "call=call-1" in started
    (finished,) = lines.named("tool_finished")
    assert "tool=list_demos" in finished and "status=" in finished and "duration_ms=" in finished
    assert "tools=1" in lines.named("turn_finished")[0]


async def test_signing_in_logs_the_outcome_but_never_the_code(lines: _Lines) -> None:
    # Given an agent behind a pass code
    agent = an_agent(ScriptedChatModel.replying(answer("hi")), access_code=CODE)

    # When someone signs in wrongly, then rightly
    for code in ("guess", CODE):
        await agent.http("POST", "/auth/session", body=json.dumps({"code": code}).encode())

    # Then both attempts are logged by outcome, and neither code appears anywhere
    assert [line.split("result=")[1] for line in lines.named("auth_signin")] == ["refused", "ok"]
    assert CODE not in lines.all() and "guess" not in lines.all()


async def test_a_refused_caller_is_logged_with_what_it_tried(lines: _Lines) -> None:
    # Given an agent behind a pass code
    agent = an_agent(ScriptedChatModel.replying(answer("hi")), access_code=CODE)

    # When an rpc and a frame are asked for without a session
    with pytest.raises(ConnectError):
        await agent.client(CHAT_SERVICE).unary("ListModels", chat_pb2.ListModelsRequest())
    await agent.http("GET", "/frames/run-7/1.jpg")

    # Then each refusal names its surface and target
    refused = lines.named("auth_refused")
    assert any("surface=rpc" in line and "ListModels" in line for line in refused)
    assert any("surface=http" in line and "target=/frames/run-7/1.jpg" in line for line in refused)


def test_the_station_logs_starts_stops_and_idle_stops(lines: _Lines) -> None:
    # Given a stub station on a manual clock
    clock = FakeClock()
    station = StubStationControl(clock=clock, idle_timeout_s=60)

    # When it is started, stopped, started again and left idle past its timeout
    station.start()
    station.stop()
    station.start()
    clock.advance(60)
    station.check_idle()

    # Then each transition is a station line with its action and resulting state
    actions = [(_field(line, "action"), _field(line, "state")) for line in lines.named("station")]
    assert actions == [
        ("start", "ready"),
        ("stop", "off"),
        ("start", "ready"),
        ("idle_stop", "off"),
    ]


def _field(line: str, key: str) -> str:
    return next(part.split("=", 1)[1] for part in line.split() if part.startswith(f"{key}="))
