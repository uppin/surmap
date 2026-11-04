"""`turn_event_to_proto`: each runtime event as the `surmap.agent.v1.TurnEvent` the chat
stream carries."""

from __future__ import annotations

import json

import pytest

from surmap.agent.contracts import ExecutionMode, ExecutionPolicy, OnTimeout
from surmap.agent.proto import chat_pb2, execution_pb2
from surmap.agent.runtime.events import (
    FinishReason,
    JobUpdate,
    SteerApplied,
    SubagentMessage,
    SubagentStatus,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnError,
    TurnEvent,
    TurnFinished,
)
from surmap.agent.runtime.jobs import Completed, Detached, Failed, Job, JobState
from surmap.agent.server.binding import ToolImage
from surmap.agent.server.chat_service import turn_event_to_proto
from tests.agent_server_fakes import a_jpeg

FRAME_JPEG = a_jpeg()


def as_proto(event: TurnEvent) -> chat_pb2.TurnEvent:
    """The event as the seventh of turn `t-2` in `conv-1`."""
    return turn_event_to_proto(event, conversation_id="conv-1", turn_id="t-2", seq=7)


def a_job(state: JobState = JobState.RUNNING, detail: str = "") -> Job:
    return Job(job_id="j-3", tool="run_demo", state=state, started_at=12.0, detail=detail)


def a_finished_call(outcome: Completed | Detached | Failed) -> chat_pb2.ToolCallFinished:
    return as_proto(
        ToolCallFinished(call_id="call-1", tool="run_demo", outcome=outcome)
    ).tool_call_finished


def test_an_event_carries_its_conversation_turn_and_position() -> None:
    # Given a piece of answer text
    event = TextDelta(text="Three ")

    # When it is mapped
    mapped = as_proto(event)

    # Then it names conv-1, turn t-2 and position 7
    assert (mapped.conversation_id, mapped.turn_id, mapped.seq) == ("conv-1", "t-2", 7)


def test_a_text_delta_becomes_text_delta() -> None:
    # Given a piece of answer text
    event = TextDelta(text="Three ")

    # When it is mapped
    mapped = as_proto(event)

    # Then the text is carried as text_delta
    assert (mapped.WhichOneof("event"), mapped.text_delta) == ("text_delta", "Three ")


def test_a_started_call_carries_its_arguments_as_json() -> None:
    # Given run_demo started on EuRoC
    event = ToolCallStarted(
        call_id="call-1",
        tool="run_demo",
        arguments={"dataset": "euroc-v1-01-easy", "max_frames": 40},
        execution=ExecutionPolicy(ExecutionMode.SYNC, 30, OnTimeout.DETACH),
    )

    # When it is mapped
    started = as_proto(event).tool_call_started

    # Then the arguments read back as the model gave them
    assert (started.call_id, started.tool, json.loads(started.arguments_json)) == (
        "call-1",
        "run_demo",
        {"dataset": "euroc-v1-01-easy", "max_frames": 40},
    )


def test_a_started_call_carries_the_policy_it_runs_with() -> None:
    # Given run_demo started under SYNC, 30 s, DETACH
    event = ToolCallStarted(
        call_id="call-1",
        tool="run_demo",
        arguments={},
        execution=ExecutionPolicy(ExecutionMode.SYNC, 30, OnTimeout.DETACH),
    )

    # When it is mapped
    started = as_proto(event).tool_call_started

    # Then the proto policy says the same
    assert started.execution == execution_pb2.ExecutionPolicy(
        mode=execution_pb2.SYNC, timeout_s=30, on_timeout=execution_pb2.DETACH
    )


def test_a_completed_call_succeeds_with_its_result_as_json() -> None:
    # Given a call that returned a run
    outcome = Completed(job_id="j-3", result={"run": {"run_id": "run-7", "frames": 42}})

    # When its finish is mapped
    finished = a_finished_call(outcome)

    # Then it succeeded with that result
    assert (finished.status, json.loads(finished.result_json)) == (
        chat_pb2.ToolCallFinished.SUCCEEDED,
        {"run": {"run_id": "run-7", "frames": 42}},
    )


def test_a_completed_call_s_image_goes_in_the_image_field() -> None:
    # Given a call that returned a frame
    outcome = Completed(job_id="j-3", result={"image": ToolImage(FRAME_JPEG, "image/jpeg")})

    # When its finish is mapped
    finished = a_finished_call(outcome)

    # Then the bytes and media type are carried as the image
    assert (finished.image, finished.media_type) == (FRAME_JPEG, "image/jpeg")


def test_a_failed_call_fails_with_its_error_as_json() -> None:
    # Given a call that failed
    outcome = Failed(job_id="j-3", error="no run run-404")

    # When its finish is mapped
    finished = a_finished_call(outcome)

    # Then it failed with that error
    assert (finished.status, json.loads(finished.result_json)) == (
        chat_pb2.ToolCallFinished.FAILED,
        {"error": "no run run-404"},
    )


def test_a_detached_call_carries_the_job_it_became() -> None:
    # Given a call a steer detached
    outcome = Detached(job=a_job(detail="detached by steer"), detail="detached by steer")

    # When its finish is mapped
    finished = a_finished_call(outcome)

    # Then it is DETACHED with the running job's handle
    assert (finished.status, finished.job) == (
        chat_pb2.ToolCallFinished.DETACHED,
        execution_pb2.JobHandle(
            job_id="j-3",
            tool="run_demo",
            status=execution_pb2.RUNNING,
            detail="detached by steer",
        ),
    )


def test_a_job_update_carries_the_job_s_handle() -> None:
    # Given a job that succeeded during the turn
    event = JobUpdate(job=a_job(JobState.SUCCEEDED))

    # When it is mapped
    mapped = as_proto(event)

    # Then the update is that job's handle
    assert mapped.job_update == execution_pb2.JobHandle(
        job_id="j-3", tool="run_demo", status=execution_pb2.SUCCEEDED
    )


def test_a_steer_applied_carries_the_guidance_and_the_detached_calls() -> None:
    # Given a steer that detached one call
    event = SteerApplied(text="use KITTI instead", detached_call_ids=("call-1",))

    # When it is mapped
    mapped = as_proto(event)

    # Then the guidance and call ids are carried
    assert mapped.steer_applied == chat_pb2.SteerApplied(
        text="use KITTI instead", detached_call_ids=["call-1"]
    )


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("stop", chat_pb2.TurnFinished.STOP),
        ("round_cap", chat_pb2.TurnFinished.LENGTH),
        ("repeated_failure", chat_pb2.TurnFinished.STOP),
        ("cancelled", chat_pb2.TurnFinished.CANCELLED),
        ("error", chat_pb2.TurnFinished.ERROR),
    ],
)
def test_a_finished_turn_carries_its_reason(
    reason: FinishReason, expected: chat_pb2.TurnFinished.Reason
) -> None:
    # Given a turn that ended for this reason
    event = TurnFinished(reason=reason)

    # When it is mapped
    mapped = as_proto(event)

    # Then the proto reason matches
    assert mapped.turn_finished.reason == expected


def test_a_turn_error_carries_its_message() -> None:
    # Given a turn that failed
    event = TurnError(message="Meta Responses returned no output text")

    # When it is mapped
    mapped = as_proto(event)

    # Then the message is carried as error
    assert mapped.error == chat_pb2.TurnError(message="Meta Responses returned no output text")


def test_a_subagent_message_becomes_subagent_message() -> None:
    # Given a subagent's message to the main agent
    event = SubagentMessage(subagent_id="sa-1", name="scene-builder", text="Which side burns?")

    # When it is mapped
    mapped = as_proto(event)

    # Then it carries the subagent and its text
    assert mapped.subagent_message == chat_pb2.SubagentMessage(
        subagent_id="sa-1", name="scene-builder", text="Which side burns?"
    )


def test_a_subagent_status_becomes_subagent_status() -> None:
    # Given the scene builder's status as it works
    event = SubagentStatus(
        subagent_id="sa-1",
        name="scene-builder",
        job_id="j-2",
        state=JobState.RUNNING,
        detail="Placing the house",
    )

    # When it is mapped
    mapped = as_proto(event)

    # Then it carries the subagent, its job, its state and what it reported
    assert mapped.subagent_status == chat_pb2.SubagentStatus(
        subagent_id="sa-1",
        name="scene-builder",
        job_id="j-2",
        status=execution_pb2.RUNNING,
        detail="Placing the house",
    )
