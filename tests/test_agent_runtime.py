"""The agent turn loop: text answers, tool results fed back, caps, tool failures, and the
graph and tool bindings underneath it. A scripted model drives a real graph, runner and store."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from surmap.agent.contracts import ExecutionMode, OnTimeout
from surmap.agent.runtime.events import ToolCallFinished, ToolCallStarted
from surmap.agent.runtime.graph import TurnCaps, build_turn_graph, turn_input
from surmap.agent.runtime.jobs import Completed, Failed, JobRunner
from surmap.agent.runtime.tools import bind_contract_tool
from tests.agent_fakes import (
    TIMEOUT_SCALE,
    FakeToolHandler,
    ScriptedChatModel,
    a_session,
    a_tool_contract,
    answer,
    calling,
    collect,
    errors_in,
    finish_reason,
    human_texts,
    mentions,
    outcome_of,
    resolve_locally,
    text_deltas,
    tool_call,
    tool_message_for,
)

EUROC = "euroc-v1-01-easy"
RUN_DEMO = a_tool_contract(
    "run_demo",
    timeout_s=1,
    on_timeout=OnTimeout.FAIL,
    properties={"dataset": {"type": "string"}},
)
GET_RUN = a_tool_contract("get_run", timeout_s=1, properties={"run_id": {"type": "string"}})


def run_the_demo(call_id: str = "call-1") -> AIMessage:
    return calling(tool_call("run_demo", call_id, dataset=EUROC))


# --- acceptance: the turn loop -------------------------------------------------------------


async def test_a_model_answering_without_tools_finishes_with_stop_and_streams_its_text() -> None:
    # Given a model that answers in one sentence
    rig = a_session(ScriptedChatModel.replying(answer("The run found two boxes.")))

    # When a person asks a question
    events = await collect(rig.session.run_turn("What did the run find?"))

    # Then the answer streams word by word and the turn ends with reason stop
    assert text_deltas(events) == ["The ", "run ", "found ", "two ", "boxes."]
    assert finish_reason(events) == "stop"


async def test_a_tool_result_is_fed_back_as_the_last_message_of_the_models_next_history() -> None:
    # Given a model that runs the demo, then answers
    demo = FakeToolHandler.returning({"run_id": "run-7"})
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("Run run-7 is ready."))
    rig = a_session(model, (RUN_DEMO, demo))

    # When the turn runs
    await collect(rig.session.run_turn("Run the EuRoC demo"))

    # Then the model's second call ends with the demo's result for call-1
    last = model.history_of_call(2)[-1]
    assert isinstance(last, ToolMessage)
    assert last.tool_call_id == "call-1"
    assert mentions(last, "run-7")


async def test_a_tool_call_is_announced_before_it_finishes_with_its_inline_result() -> None:
    # Given a model that runs the demo, then answers
    demo = FakeToolHandler.returning({"run_id": "run-7"})
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("Done."))
    rig = a_session(model, (RUN_DEMO, demo))

    # When the turn runs
    events = await collect(rig.session.run_turn("Run the EuRoC demo"))

    # Then the call started with the model's arguments, then completed with the result
    started = [e for e in events if isinstance(e, ToolCallStarted)]
    finished = [e for e in events if isinstance(e, ToolCallFinished)]
    assert [(e.call_id, e.tool, dict(e.arguments)) for e in started] == [
        ("call-1", "run_demo", {"dataset": EUROC})
    ]
    assert events.index(started[0]) < events.index(finished[0])
    assert outcome_of(events, "call-1") == Completed(job_id="j-1", result={"run_id": "run-7"})


async def test_the_round_cap_cuts_the_turn_off_and_answers_the_extra_calls_not_run() -> None:
    # Given a model that keeps asking for the run, and a cap of two tool rounds
    get_run = FakeToolHandler.returning({"state": "running"})
    model = ScriptedChatModel.replying(calling(tool_call("get_run", "call-1", run_id="run-7")))
    rig = a_session(model, (GET_RUN, get_run), caps=TurnCaps(max_rounds=2))

    # When the turn runs
    events = await collect(rig.session.run_turn("Is run-7 done?"))

    # Then two rounds ran, and the call asked for after them was answered "Not run"
    assert finish_reason(events) == "round_cap"
    assert len(get_run.calls) == 2
    assert mentions(tool_message_for(rig.history, "call-1"), "Not run")


async def test_three_identical_failing_calls_cut_the_turn_off() -> None:
    # Given a model that keeps retrying a demo whose camera is offline
    demo = FakeToolHandler.failing("camera offline")
    model = ScriptedChatModel.replying(run_the_demo("call-1"))
    rig = a_session(model, (RUN_DEMO, demo))

    # When the turn runs
    events = await collect(rig.session.run_turn("Run the EuRoC demo"))

    # Then the identical call failed three times and the turn was cut off
    assert finish_reason(events) == "repeated_failure"
    assert len(demo.calls) == 3


async def test_a_failing_handler_becomes_a_failed_tool_result_not_a_turn_error() -> None:
    # Given a demo whose camera is offline, and a model that explains the failure
    demo = FakeToolHandler.failing("camera offline")
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("The camera is offline."))
    rig = a_session(model, (RUN_DEMO, demo))

    # When the turn runs
    events = await collect(rig.session.run_turn("Run the EuRoC demo"))

    # Then the failure went back to the model as an error result and the turn ended normally
    result = tool_message_for(model.history_of_call(2), "call-1")
    assert result.status == "error"
    assert mentions(result, "camera offline")
    assert isinstance(outcome_of(events, "call-1"), Failed)
    assert errors_in(events) == []
    assert finish_reason(events) == "stop"


async def test_the_turn_appends_the_question_and_its_rounds_to_the_conversation() -> None:
    # Given a model that runs the demo, then answers
    demo = FakeToolHandler.returning({"run_id": "run-7"})
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("Run run-7 is ready."))
    rig = a_session(model, (RUN_DEMO, demo))

    # When the turn runs
    await collect(rig.session.run_turn("Run the EuRoC demo"))

    # Then the store holds the question, the call, its result and the answer, in order
    assert [type(m).__name__ for m in rig.history] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
    ]
    assert human_texts(rig.history) == ["Run the EuRoC demo"]


async def test_the_model_is_bound_to_every_tool_of_the_session() -> None:
    # Given a session with the demo tool and the job tools
    model = ScriptedChatModel.replying(answer("Hello."))
    rig = a_session(model, (RUN_DEMO, FakeToolHandler.returning({})))

    # When a turn runs
    await collect(rig.session.run_turn("Hi"))

    # Then the model was bound to the demo tool and the four job tools
    assert set(model.bound_tool_names[-1]) == {
        "run_demo",
        "wait_for_jobs",
        "get_job",
        "cancel_job",
        "list_jobs",
    }


# --- the graph -----------------------------------------------------------------------------


def no_pending() -> list[BaseMessage]:
    return []


async def test_the_graph_appends_the_models_answer_and_records_why_it_stopped() -> None:
    # Given a turn graph over a model that answers at once
    model = ScriptedChatModel.replying(answer("Hello."))
    graph = build_turn_graph(model, [], no_pending, TurnCaps())

    # When it runs on one question
    state = await graph.ainvoke(turn_input([HumanMessage("Hi")]))

    # Then the answer follows the question and the reason is stop
    assert [m.text for m in state["messages"]] == ["Hi", "Hello."]
    assert state["finish_reason"] == "stop"


async def test_the_graph_drains_pending_messages_before_each_model_call() -> None:
    # Given a steer that becomes pending once the model has made its first call
    steer: list[BaseMessage] = [HumanMessage("Look at the car instead")]
    demo = FakeToolHandler.returning({"run_id": "run-7"})
    runner = JobRunner(timeout_scale=TIMEOUT_SCALE)
    tool = bind_contract_tool(RUN_DEMO, demo, runner, resolve=resolve_locally)
    model = ScriptedChatModel.replying(run_the_demo("call-1"), answer("Looking at the car."))

    def drain() -> list[BaseMessage]:
        return [steer.pop()] if model.calls == 1 and steer else []

    graph = build_turn_graph(model, [tool], drain, TurnCaps())

    # When the graph runs two rounds
    await graph.ainvoke(turn_input([HumanMessage("Run the EuRoC demo")]))

    # Then the model's second call saw the pending message
    assert human_texts(model.history_of_call(2))[-1] == "Look at the car instead"


# --- caps ----------------------------------------------------------------------------------


def test_the_caps_default_to_thirty_rounds_and_three_identical_failures() -> None:
    # Given no environment override
    env: dict[str, str] = {}

    # When the caps are read from it
    caps = TurnCaps.from_env(env)

    # Then they are the defaults
    assert caps == TurnCaps(max_rounds=30, max_identical_failures=3)


def test_the_round_cap_comes_from_surmap_agent_max_rounds() -> None:
    # Given an environment that lowers the round cap
    env = {"SURMAP_AGENT_MAX_ROUNDS": "12"}

    # When the caps are read from it
    caps = TurnCaps.from_env(env)

    # Then the round cap is 12
    assert caps.max_rounds == 12


# --- binding a contract --------------------------------------------------------------------


def test_a_bound_tool_offers_the_contract_as_a_function_definition() -> None:
    # Given the demo contract bound to a handler
    runner = JobRunner(timeout_scale=TIMEOUT_SCALE)
    tool = bind_contract_tool(
        RUN_DEMO, FakeToolHandler.returning({}), runner, resolve=resolve_locally
    )

    # When its model schema is read
    schema = tool.model_schema()

    # Then it names the tool, describes it and takes the contract's input schema
    assert schema == {
        "type": "function",
        "function": {
            "name": "run_demo",
            "description": RUN_DEMO.description,
            "parameters": dict(RUN_DEMO.input_schema),
        },
    }


def test_preparing_a_call_strips_execution_and_resolves_the_override() -> None:
    # Given the demo contract, SYNC by default
    runner = JobRunner(timeout_scale=TIMEOUT_SCALE)
    tool = bind_contract_tool(
        RUN_DEMO, FakeToolHandler.returning({}), runner, resolve=resolve_locally
    )

    # When the model asks for it to run ASYNC
    call = tool.prepare({"dataset": EUROC, "execution": {"mode": "ASYNC"}})

    # Then the handler's arguments lose execution and the policy is ASYNC
    assert dict(call.arguments) == {"dataset": EUROC}
    assert call.execution.mode is ExecutionMode.ASYNC


async def test_running_a_prepared_call_hands_the_handler_its_arguments() -> None:
    # Given the demo contract bound to a recording handler
    demo = FakeToolHandler.returning({"run_id": "run-7"})
    runner = JobRunner(timeout_scale=TIMEOUT_SCALE)
    tool = bind_contract_tool(RUN_DEMO, demo, runner, resolve=resolve_locally)

    # When a call with an execution override runs
    outcome = await tool.run(tool.prepare({"dataset": EUROC, "execution": {"timeout_s": 2}}))

    # Then the handler saw only the dataset and the result came back inline
    assert demo.calls == [{"dataset": EUROC}]
    assert outcome == Completed(job_id="j-1", result={"run_id": "run-7"})
