"""Every tool call is a job: sync within and past its timeout, async handles, job notices,
waiting, cancelling, and the job tools the model calls. Timeouts are scaled to 0.05 s; held
handlers are released by the test, never by a clock."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from langchain_core.messages import AIMessage

from surmap.agent.contracts import ExecutionMode, ExecutionPolicy, OnTimeout, ToolContract
from surmap.agent.runtime.events import ToolCallFinished, TurnEvent
from surmap.agent.runtime.jobs import (
    Completed,
    Detached,
    Failed,
    JobNotice,
    JobRunner,
    JobState,
)
from surmap.agent.runtime.tools import BoundTool, job_tools
from tests.agent_fakes import (
    TIMEOUT_SCALE,
    FakeToolHandler,
    ScriptedChatModel,
    a_session,
    a_tool_contract,
    agent_job_contracts,
    answer,
    calling,
    collect,
    mentions,
    outcome_of,
    resolve_locally,
    tool_call,
    tool_message_for,
    until_held,
)

EUROC = "euroc-v1-01-easy"
RUN_DEMO = a_tool_contract("run_demo", properties={"dataset": {"type": "string"}})
DEMO_ARGS: Mapping[str, object] = {"dataset": EUROC}
FINISHED_RUN: Mapping[str, object] = {"run_id": "run-7", "frames": 120}


def sync(timeout_s: int, on_timeout: OnTimeout) -> ExecutionPolicy:
    return ExecutionPolicy(mode=ExecutionMode.SYNC, timeout_s=timeout_s, on_timeout=on_timeout)


ASYNC = ExecutionPolicy(mode=ExecutionMode.ASYNC, timeout_s=0, on_timeout=OnTimeout.FAIL)
LONG_SYNC = sync(300, OnTimeout.DETACH)
"""A SYNC wait no test reaches the end of: 15 s at the test scale."""


def a_runner() -> JobRunner:
    return JobRunner(timeout_scale=TIMEOUT_SCALE)


def run_demo_with(**execution: object) -> AIMessage:
    return calling(tool_call("run_demo", "call-1", dataset=EUROC, execution=execution))


def the_job_tool(runner: JobRunner, name: str) -> BoundTool:
    return {tool.name: tool for tool in job_tools(runner, agent_job_contracts())}[name]


async def a_finished_job(runner: JobRunner, contract: ToolContract = RUN_DEMO) -> str:
    outcome = await runner.call(
        contract, DEMO_ARGS, FakeToolHandler.returning(FINISHED_RUN), policy=ASYNC
    )
    assert isinstance(outcome, Detached)
    await runner.wait([outcome.job.job_id], "all", timeout_s=1.0)
    return outcome.job.job_id


# --- acceptance: through a session ---------------------------------------------------------


async def test_a_sync_call_that_finishes_within_its_timeout_returns_its_result_inline() -> None:
    # Given a demo that finishes at once, SYNC with a timeout of 1
    demo = FakeToolHandler.returning(FINISHED_RUN)
    model = ScriptedChatModel.replying(
        calling(tool_call("run_demo", "call-1", dataset=EUROC)), answer("Run run-7 is ready.")
    )
    rig = a_session(model, (RUN_DEMO, demo))

    # When the turn runs
    events = await collect(rig.session.run_turn("Run the EuRoC demo"))

    # Then the call completed with the demo's result
    assert outcome_of(events, "call-1") == Completed(job_id="j-1", result=FINISHED_RUN)
    assert mentions(tool_message_for(model.history_of_call(2), "call-1"), "run-7")


async def test_a_sync_call_past_its_timeout_with_detach_returns_a_job_handle() -> None:
    # Given a demo that holds, SYNC with a timeout of 1 and DETACH
    demo = FakeToolHandler.holding(FINISHED_RUN)
    model = ScriptedChatModel.replying(
        run_demo_with(on_timeout="DETACH"), answer("The demo is running as j-1.")
    )
    rig = a_session(model, (RUN_DEMO, demo))

    # When the turn runs past the timeout
    events = await collect(rig.session.run_turn("Run the EuRoC demo"))

    # Then the model got the running job's handle instead of a result
    outcome = outcome_of(events, "call-1")
    assert isinstance(outcome, Detached)
    assert (outcome.job.job_id, outcome.job.state) == ("j-1", JobState.RUNNING)
    assert mentions(tool_message_for(model.history_of_call(2), "call-1"), "j-1")


async def test_a_detached_jobs_result_arrives_as_a_notice_before_the_models_next_call() -> None:
    # Given a demo that detaches past its timeout, and a model that then waits for the job
    demo = FakeToolHandler.holding(FINISHED_RUN)
    model = ScriptedChatModel.replying(
        run_demo_with(on_timeout="DETACH"),
        calling(tool_call("wait_for_jobs", "call-2", job_ids=["j-1"], mode="ALL")),
        answer("Run run-7 is ready."),
    )
    rig = a_session(model, (RUN_DEMO, demo))

    # When the demo is released as soon as it has detached
    events: list[TurnEvent] = []
    async for event in rig.session.run_turn("Run the EuRoC demo"):
        events.append(event)
        if isinstance(event, ToolCallFinished) and isinstance(event.outcome, Detached):
            demo.release()

    # Then the model's next call after the job ended carries the job's notice
    assert any(
        mentions(message, "Job j-1 run_demo succeeded") for message in model.history_of_call(3)
    )


async def test_a_sync_call_past_its_timeout_with_fail_is_cancelled_and_reported() -> None:
    # Given a demo that holds, SYNC with a timeout of 1 and FAIL
    demo = FakeToolHandler.holding(FINISHED_RUN)
    model = ScriptedChatModel.replying(
        run_demo_with(on_timeout="FAIL"), answer("The demo timed out.")
    )
    rig = a_session(model, (RUN_DEMO, demo))

    # When the turn runs past the timeout
    events = await collect(rig.session.run_turn("Run the EuRoC demo"))

    # Then the demo was cancelled and the model got a failed result naming the timeout
    assert demo.was_cancelled
    assert isinstance(outcome_of(events, "call-1"), Failed)
    result = tool_message_for(model.history_of_call(2), "call-1")
    assert result.status == "error"
    assert mentions(result, "timed out")


async def test_an_async_call_returns_a_handle_at_once_and_wait_for_jobs_returns_its_result() -> (
    None
):
    # Given a model that runs the demo ASYNC, then waits for it
    demo = FakeToolHandler.returning(FINISHED_RUN)
    model = ScriptedChatModel.replying(
        run_demo_with(mode="ASYNC"),
        calling(tool_call("wait_for_jobs", "call-2", job_ids=["j-1"], mode="ALL")),
        answer("Run run-7 is ready."),
    )
    rig = a_session(model, (RUN_DEMO, demo))

    # When the turn runs
    events = await collect(rig.session.run_turn("Run the EuRoC demo in the background"))

    # Then the call became job j-1 at once, and waiting returned the demo's result
    detached = outcome_of(events, "call-1")
    assert isinstance(detached, Detached)
    assert detached.job.job_id == "j-1"
    assert mentions(tool_message_for(model.history_of_call(3), "call-2"), "run-7")


async def test_a_job_ending_while_the_session_is_idle_comes_out_of_idle_events() -> None:
    # Given a turn that left the demo running ASYNC as j-1
    demo = FakeToolHandler.holding(FINISHED_RUN)
    model = ScriptedChatModel.replying(run_demo_with(mode="ASYNC"), answer("Started job j-1."))
    rig = a_session(model, (RUN_DEMO, demo))
    await collect(rig.session.run_turn("Run the EuRoC demo in the background"))
    idle = rig.session.idle_events()

    # When the demo finishes after the turn
    demo.release()
    notice = await anext(idle)

    # Then the idle session emits the job's notice
    assert isinstance(notice, JobNotice)
    assert (notice.job.job_id, notice.job.state) == ("j-1", JobState.SUCCEEDED)
    assert "Job j-1 run_demo succeeded" in notice.text


# --- the runner ----------------------------------------------------------------------------


async def test_a_sync_call_within_its_timeout_completes_and_its_job_succeeds() -> None:
    # Given a runner and a demo that finishes at once
    runner = a_runner()

    # When the demo is called SYNC
    outcome = await runner.call(
        RUN_DEMO,
        DEMO_ARGS,
        FakeToolHandler.returning(FINISHED_RUN),
        policy=sync(1, OnTimeout.FAIL),
    )

    # Then it completed inline and its job succeeded with the result
    assert outcome == Completed(job_id="j-1", result=FINISHED_RUN)
    job = runner.get("j-1")
    assert job is not None
    assert (job.state, job.result) == (JobState.SUCCEEDED, FINISHED_RUN)


async def test_a_detached_job_keeps_running_and_queues_a_notice_when_it_ends() -> None:
    # Given a demo that detached after its SYNC timeout
    runner = a_runner()
    demo = FakeToolHandler.holding(FINISHED_RUN)
    outcome = await runner.call(RUN_DEMO, DEMO_ARGS, demo, policy=sync(1, OnTimeout.DETACH))

    # When the demo finishes
    demo.release()
    notice = await runner.notices.get()

    # Then the job was running when it detached, and its notice names its success
    assert isinstance(outcome, Detached)
    assert outcome.job.state is JobState.RUNNING
    assert isinstance(notice, JobNotice)
    assert (notice.job.job_id, notice.job.state) == ("j-1", JobState.SUCCEEDED)
    assert notice.text.startswith("Job j-1 run_demo succeeded")


async def test_a_fail_timeout_cancels_the_handler_and_fails_the_job() -> None:
    # Given a demo that never finishes by itself
    runner = a_runner()
    demo = FakeToolHandler.holding(FINISHED_RUN)

    # When it is called SYNC with FAIL
    outcome = await runner.call(RUN_DEMO, DEMO_ARGS, demo, policy=sync(1, OnTimeout.FAIL))

    # Then the handler was cancelled and the call failed with a timeout
    assert demo.was_cancelled
    assert isinstance(outcome, Failed)
    assert "timed out" in outcome.error
    job = runner.get("j-1")
    assert job is not None
    assert job.state is JobState.FAILED


async def test_an_async_call_detaches_at_once_without_waiting_for_the_handler() -> None:
    # Given a demo that holds
    runner = a_runner()
    demo = FakeToolHandler.holding(FINISHED_RUN)

    # When it is called ASYNC
    outcome = await runner.call(RUN_DEMO, DEMO_ARGS, demo, policy=ASYNC)

    # Then the call is a running job handle with detail "async"
    assert isinstance(outcome, Detached)
    assert (outcome.job.job_id, outcome.job.state, outcome.detail) == (
        "j-1",
        JobState.RUNNING,
        "async",
    )


async def test_a_raising_handler_fails_the_call_with_its_error() -> None:
    # Given a demo whose camera is offline
    runner = a_runner()

    # When it is called SYNC
    outcome = await runner.call(
        RUN_DEMO, DEMO_ARGS, FakeToolHandler.failing("camera offline"), policy=LONG_SYNC
    )

    # Then the call failed with the handler's error
    assert isinstance(outcome, Failed)
    assert "camera offline" in outcome.error


async def test_detaching_blocking_calls_hands_each_waiting_caller_a_handle() -> None:
    # Given a SYNC demo call that is waiting on its handler
    runner = a_runner()
    demo = FakeToolHandler.holding(FINISHED_RUN)
    waiting = runner.call(RUN_DEMO, DEMO_ARGS, demo, policy=LONG_SYNC)
    call = asyncio.ensure_future(waiting)
    await until_held(demo, call)

    # When every blocking call is detached
    detached = runner.detach_blocking("detached by steer")
    outcome = await call

    # Then the one waiting call got a handle naming why it detached
    assert detached == 1
    assert isinstance(outcome, Detached)
    assert outcome.detail == "detached by steer"


async def test_job_ids_count_up_and_jobs_are_listed_newest_first() -> None:
    # Given a runner that ran two jobs
    runner = a_runner()
    first = await a_finished_job(runner)
    second = await a_finished_job(runner)

    # When its jobs are listed
    listed = [job.job_id for job in runner.jobs()]

    # Then the ids count up from j-1 and the newest is first
    assert (first, second) == ("j-1", "j-2")
    assert listed == ["j-2", "j-1"]


async def test_waiting_for_any_returns_when_the_first_job_ends() -> None:
    # Given one job that has finished and one that holds
    runner = a_runner()
    finished = await a_finished_job(runner)
    held = await runner.call(RUN_DEMO, DEMO_ARGS, FakeToolHandler.holding(), policy=ASYNC)
    assert isinstance(held, Detached)

    # When the model waits for any of the two
    waited = await runner.wait([finished, held.job.job_id], "any", timeout_s=1.0)

    # Then the wait met its mode, listing both jobs in request order
    assert not waited.timed_out
    assert [(job.job_id, job.state) for job in waited.jobs] == [
        ("j-1", JobState.SUCCEEDED),
        ("j-2", JobState.RUNNING),
    ]


async def test_waiting_for_all_times_out_while_a_job_still_runs() -> None:
    # Given a job that holds
    runner = a_runner()
    held = await runner.call(RUN_DEMO, DEMO_ARGS, FakeToolHandler.holding(), policy=ASYNC)
    assert isinstance(held, Detached)

    # When the model waits for all of them for 0.05 s
    waited = await runner.wait([held.job.job_id], "all", timeout_s=TIMEOUT_SCALE)

    # Then the wait timed out with the job still running
    assert waited.timed_out
    assert [job.state for job in waited.jobs] == [JobState.RUNNING]


async def test_cancelling_a_running_job_cancels_its_handler() -> None:
    # Given a demo running ASYNC
    runner = a_runner()
    demo = FakeToolHandler.holding()
    await runner.call(RUN_DEMO, DEMO_ARGS, demo, policy=ASYNC)
    await demo.started.wait()

    # When the job is cancelled
    cancelled = runner.cancel("j-1")
    await runner.wait(["j-1"], "all", timeout_s=1.0)

    # Then the handler was cancelled and the job says so
    assert cancelled
    assert demo.was_cancelled
    job = runner.get("j-1")
    assert job is not None
    assert job.state is JobState.CANCELLED


async def test_cancelling_a_finished_job_leaves_it_as_it_is() -> None:
    # Given a job that has succeeded
    runner = a_runner()
    job_id = await a_finished_job(runner)

    # When it is cancelled
    cancelled = runner.cancel(job_id)

    # Then nothing changed
    assert not cancelled
    job = runner.get(job_id)
    assert job is not None
    assert job.state is JobState.SUCCEEDED


# --- the job tools -------------------------------------------------------------------------


def test_job_tools_bind_the_four_agent_jobs_tools() -> None:
    # Given a runner
    runner = a_runner()

    # When its job tools are bound to the AgentJobs contracts
    tools = job_tools(runner, agent_job_contracts(), resolve=resolve_locally)

    # Then the model can call wait_for_jobs, get_job, cancel_job and list_jobs
    assert sorted(tool.name for tool in tools) == [
        "cancel_job",
        "get_job",
        "list_jobs",
        "wait_for_jobs",
    ]


async def test_get_job_returns_a_finished_jobs_result() -> None:
    # Given a job that has succeeded
    runner = a_runner()
    job_id = await a_finished_job(runner)
    get_job = the_job_tool(runner, "get_job")

    # When the model reads it
    outcome = await get_job.run(get_job.prepare({"job_id": job_id}))

    # Then the job comes back with its state and the demo's result
    assert isinstance(outcome, Completed)
    assert "SUCCEEDED" in str(outcome.result)
    assert "run-7" in str(outcome.result)


async def test_cancel_job_cancels_a_running_job() -> None:
    # Given a demo running ASYNC
    runner = a_runner()
    demo = FakeToolHandler.holding()
    await runner.call(RUN_DEMO, DEMO_ARGS, demo, policy=ASYNC)
    await demo.started.wait()
    cancel_job = the_job_tool(runner, "cancel_job")

    # When the model cancels it
    await cancel_job.run(cancel_job.prepare({"job_id": "j-1"}))
    await runner.wait(["j-1"], "all", timeout_s=1.0)

    # Then the demo was cancelled
    assert demo.was_cancelled


async def test_list_jobs_lists_the_conversations_jobs_newest_first() -> None:
    # Given two finished jobs
    runner = a_runner()
    await a_finished_job(runner)
    await a_finished_job(runner)
    list_jobs = the_job_tool(runner, "list_jobs")

    # When the model lists them
    outcome = await list_jobs.run(list_jobs.prepare({}))

    # Then j-2 comes before j-1
    assert isinstance(outcome, Completed)
    listing = str(outcome.result)
    assert listing.index("j-2") < listing.index("j-1")
