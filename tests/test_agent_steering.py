"""Steering and cancel: guidance pushed into a running turn detaches its blocking calls and is
the next thing the model reads; steering an idle session starts a turn; cancel ends the turn and
its jobs but keeps its completed rounds. Held handlers are released by events, never by sleeps."""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage

from surmap.agent.contracts import OnTimeout
from surmap.agent.runtime.events import SteerApplied
from surmap.agent.runtime.jobs import Detached, JobState
from surmap.agent.runtime.session import SteerQueued, TurnStarted
from tests.agent_fakes import (
    FakeToolHandler,
    ScriptedChatModel,
    a_session,
    a_tool_contract,
    answer,
    calling,
    collect,
    finish_reason,
    human_texts,
    outcome_of,
    tool_call,
    tool_message_for,
    until_held,
)

EUROC = "euroc-v1-01-easy"
STEER = "Stop and look at the car instead"
RUN_DEMO = a_tool_contract(
    "run_demo",
    timeout_s=300,
    on_timeout=OnTimeout.DETACH,
    properties={"dataset": {"type": "string"}},
)
"""A blocking demo whose timeout no test reaches: 15 s at the test scale."""
GET_RUN = a_tool_contract("get_run", timeout_s=1, properties={"run_id": {"type": "string"}})


def run_the_demo(call_id: str) -> AIMessage:
    return calling(tool_call("run_demo", call_id, dataset=EUROC))


async def test_a_steer_during_a_blocking_call_detaches_it_and_is_the_models_next_message() -> None:
    # Given a turn blocked on a demo that holds
    demo = FakeToolHandler.holding({"run_id": "run-7"})
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("Looking at the car."))
    rig = a_session(model, (RUN_DEMO, demo))
    turn = asyncio.create_task(collect(rig.session.run_turn("Run the EuRoC demo")))
    await until_held(demo, turn)

    # When the person steers while the demo runs
    steered = rig.session.steer(STEER)
    events = await turn

    # Then the demo detached by steer and the steer was the last human message the model saw
    assert steered == SteerQueued(detached=1)
    outcome = outcome_of(events, "call-1")
    assert isinstance(outcome, Detached)
    assert outcome.detail == "detached by steer"
    assert human_texts(model.history_of_call(2))[-1] == STEER
    assert finish_reason(events) == "stop"


async def test_a_steer_during_a_blocking_call_is_reported_with_the_calls_it_detached() -> None:
    # Given a turn blocked on a demo that holds
    demo = FakeToolHandler.holding({"run_id": "run-7"})
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("Looking at the car."))
    rig = a_session(model, (RUN_DEMO, demo))
    turn = asyncio.create_task(collect(rig.session.run_turn("Run the EuRoC demo")))
    await until_held(demo, turn)

    # When the person steers while the demo runs
    rig.session.steer(STEER)
    events = await turn

    # Then the turn reports the steer and the call it detached
    applied = [event for event in events if isinstance(event, SteerApplied)]
    assert applied == [SteerApplied(text=STEER, detached_call_ids=("call-1",))]


async def test_a_detached_call_keeps_running_as_a_job_after_the_steer() -> None:
    # Given a turn whose blocking demo was detached by a steer
    demo = FakeToolHandler.holding({"run_id": "run-7"})
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("Looking at the car."))
    rig = a_session(model, (RUN_DEMO, demo))
    turn = asyncio.create_task(collect(rig.session.run_turn("Run the EuRoC demo")))
    await until_held(demo, turn)

    # When the steer has been applied and the turn ended
    rig.session.steer(STEER)
    await turn

    # Then the demo was not cancelled: its job is still running
    job = rig.runner.get("j-1")
    assert job is not None
    assert job.state is JobState.RUNNING
    assert not demo.was_cancelled


async def test_a_steer_while_idle_starts_a_turn_that_opens_with_it() -> None:
    # Given an idle session
    model = ScriptedChatModel.replying(answer("Looking at the car."))
    rig = a_session(model)

    # When the person steers
    steered = rig.session.steer(STEER)
    assert isinstance(steered, TurnStarted)
    events = await collect(steered.events)

    # Then a turn ran with the steer as the model's message
    assert human_texts(model.history_of_call(1)) == [STEER]
    assert finish_reason(events) == "stop"


async def test_cancel_ends_the_turn_and_cancels_its_running_job() -> None:
    # Given a turn blocked on a demo that holds
    demo = FakeToolHandler.holding({"run_id": "run-7"})
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("Never said."))
    rig = a_session(model, (RUN_DEMO, demo))
    turn = asyncio.create_task(collect(rig.session.run_turn("Run the EuRoC demo")))
    await until_held(demo, turn)

    # When the person cancels the turn
    await rig.session.cancel()
    events = await turn

    # Then the turn ended cancelled and the demo's job was cancelled with it
    assert finish_reason(events) == "cancelled"
    assert demo.was_cancelled
    job = rig.runner.get("j-1")
    assert job is not None
    assert job.state is JobState.CANCELLED


async def test_cancel_keeps_the_rounds_that_completed_in_the_conversation() -> None:
    # Given a turn whose first round read a run and whose second blocks on a demo
    get_run = FakeToolHandler.returning({"run_id": "run-6", "state": "finished"})
    demo = FakeToolHandler.holding({"run_id": "run-7"})
    model = ScriptedChatModel.replying(
        calling(tool_call("get_run", "call-1", run_id="run-6")),
        run_the_demo("call-2"),
        answer("Never said."),
    )
    rig = a_session(model, (GET_RUN, get_run), (RUN_DEMO, demo))
    turn = asyncio.create_task(collect(rig.session.run_turn("Compare run-6 with a new run")))
    await until_held(demo, turn)

    # When the person cancels the turn
    await rig.session.cancel()
    await turn

    # Then the question and the completed first round stay in the conversation
    assert human_texts(rig.history) == ["Compare run-6 with a new run"]
    assert "run-6" in tool_message_for(rig.history, "call-1").text


async def test_a_turn_its_reader_abandons_cancels_the_call_it_was_waiting_on() -> None:
    # Given a turn blocked on a demo that holds
    demo = FakeToolHandler.holding({"run_id": "run-7"})
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("Never said."))
    rig = a_session(model, (RUN_DEMO, demo))
    turn = asyncio.create_task(collect(rig.session.run_turn("Run the EuRoC demo")))
    await until_held(demo, turn)

    # When the reader of the turn's events goes away without cancelling the session
    turn.cancel()
    await asyncio.wait({turn})
    await rig.runner.wait(["j-1"], "all", timeout_s=1.0)

    # Then the call nobody waits for any more was cancelled, not left running unreported
    assert demo.was_cancelled
    job = rig.runner.get("j-1")
    assert job is not None
    assert job.state is JobState.CANCELLED
