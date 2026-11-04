"""The `ChatService` and `AgentJobs` handlers over a `ChatHub`, and the event mapping.

`turn_event_to_proto` maps each runtime event (`surmap.agent.runtime.events`) onto one
`surmap.agent.v1.TurnEvent`:

- `TextDelta` → `text_delta`.
- `ToolCallStarted` → `tool_call_started`: the arguments as JSON, the resolved policy.
- `ToolCallFinished` → `tool_call_finished`: `SUCCEEDED` with the result as JSON (an image the
  tool returned goes in `image` / `media_type`, never into the JSON), `FAILED` with
  `{"error": ...}`, `DETACHED` with the job's handle.
- `JobUpdate` → `job_update`, the job's handle.
- `SteerApplied` → `steer_applied`.
- `SubagentMessage` → `subagent_message`.
- `SubagentStatus` → `subagent_status`, its state as the `JobStatus` its job has.
- `TurnFinished` → `turn_finished`: `stop` and `repeated_failure` → `STOP`, `round_cap` →
  `LENGTH`, `cancelled` → `CANCELLED`, `error` → `ERROR`.
- `TurnError` → `error`.

Errors: `StreamTurn` on a model id no provider builds is `INVALID_ARGUMENT`, and on a
conversation whose turn is still running `FAILED_PRECONDITION`; `GetConversation` on an unknown
conversation is `NOT_FOUND`. `AgentJobs` rpcs name their conversation in the
`CONVERSATION_HEADER` request header: `INVALID_ARGUMENT` without it, `NOT_FOUND` for an unknown
conversation or job.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from typing import TYPE_CHECKING, Any, assert_never

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext

from surmap.agent.contracts import ExecutionMode, ExecutionPolicy, OnTimeout
from surmap.agent.llm.registry import UnknownModelProvider
from surmap.agent.proto import chat_pb2, execution_pb2, jobs_pb2
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
from surmap.agent.runtime.jobs import (
    Completed,
    Detached,
    Failed,
    Job,
    JobRunner,
    JobState,
    ToolOutcome,
    WaitMode,
)
from surmap.agent.server.binding import IMAGE_KEY, ToolImage
from surmap.agent.services import Handler

if TYPE_CHECKING:
    from surmap.agent.server.hub import ChatHub, Conversation

__all__ = ["CONVERSATION_HEADER", "agent_jobs_handlers", "chat_handlers", "turn_event_to_proto"]

CONVERSATION_HEADER = "surmap-conversation-id"
"""The request header naming the conversation an `AgentJobs` rpc reads the jobs of."""

MAX_WAIT_S = 300
"""The longest one `WaitForJobs` may wait, in seconds."""
_CANCEL_SETTLE_S = 1.0
"""How long `CancelJob` lets the cancelled job settle before it reports the job's state."""

_MODES: dict[ExecutionMode, execution_pb2.ExecutionMode] = {
    ExecutionMode.SYNC: execution_pb2.SYNC,
    ExecutionMode.ASYNC: execution_pb2.ASYNC,
}
_TIMEOUTS: dict[OnTimeout, execution_pb2.OnTimeout] = {
    OnTimeout.FAIL: execution_pb2.FAIL,
    OnTimeout.DETACH: execution_pb2.DETACH,
}
_JOB_STATUS: dict[JobState, execution_pb2.JobStatus] = {
    JobState.RUNNING: execution_pb2.RUNNING,
    JobState.SUCCEEDED: execution_pb2.SUCCEEDED,
    JobState.FAILED: execution_pb2.FAILED,
    JobState.CANCELLED: execution_pb2.CANCELLED,
}
_REASONS: dict[FinishReason, chat_pb2.TurnFinished.Reason] = {
    "stop": chat_pb2.TurnFinished.STOP,
    "round_cap": chat_pb2.TurnFinished.LENGTH,
    "repeated_failure": chat_pb2.TurnFinished.STOP,
    "cancelled": chat_pb2.TurnFinished.CANCELLED,
    "error": chat_pb2.TurnFinished.ERROR,
}


def chat_handlers(hub: ChatHub) -> Mapping[str, Handler]:
    """Every `ChatService` rpc, by rpc name, as a `(request, ctx)` handler over `hub`."""

    async def stream_turn(
        request: chat_pb2.StreamTurnRequest, _ctx: RequestContext[Any, Any]
    ) -> AsyncIterator[chat_pb2.TurnEvent]:
        if hub.busy(request.conversation_id):
            raise ConnectError(
                Code.FAILED_PRECONDITION,
                f"conversation {request.conversation_id} already has a turn running",
            )
        model_id = request.model_id if request.HasField("model_id") else None
        try:
            async for event in hub.stream_turn(
                request.conversation_id, request.text, model_id=model_id
            ):
                yield event
        except UnknownModelProvider as error:
            raise ConnectError(Code.INVALID_ARGUMENT, str(error)) from error

    async def watch(
        request: chat_pb2.WatchConversationRequest, _ctx: RequestContext[Any, Any]
    ) -> AsyncIterator[chat_pb2.TurnEvent]:
        _conversation_or_refuse(hub, request.conversation_id)
        async for event in hub.watch(request.conversation_id):
            yield event

    async def steer(
        request: chat_pb2.SteerRequest, _ctx: RequestContext[Any, Any]
    ) -> chat_pb2.SteerResponse:
        return chat_pb2.SteerResponse(accepted=hub.steer(request.conversation_id, request.text))

    async def cancel_turn(
        request: chat_pb2.CancelTurnRequest, _ctx: RequestContext[Any, Any]
    ) -> chat_pb2.CancelTurnResponse:
        return chat_pb2.CancelTurnResponse(cancelled=await hub.cancel(request.conversation_id))

    async def list_models(
        _request: chat_pb2.ListModelsRequest, _ctx: RequestContext[Any, Any]
    ) -> chat_pb2.ListModelsResponse:
        listed = list(await asyncio.to_thread(hub.list_models))
        models = [
            chat_pb2.ChatModel(
                id=model.id, provider=model.provider, display_name=model.model, available=True
            )
            for model in listed
        ]
        default = hub.default_model_id
        if default not in {model.id for model in listed}:
            provider, _, name = default.partition(":")
            models.append(
                chat_pb2.ChatModel(
                    id=default,
                    provider=provider,
                    display_name=name or default,
                    available=False,
                    detail="not among the models reachable now",
                )
            )
        return chat_pb2.ListModelsResponse(models=models, default_model_id=default)

    async def get_conversation(
        request: chat_pb2.GetConversationRequest, _ctx: RequestContext[Any, Any]
    ) -> chat_pb2.GetConversationResponse:
        conversation = _conversation_or_refuse(hub, request.conversation_id)
        return chat_pb2.GetConversationResponse(
            conversation_id=request.conversation_id, events=conversation.events
        )

    return {
        "StreamTurn": stream_turn,
        "WatchConversation": watch,
        "Steer": steer,
        "CancelTurn": cancel_turn,
        "ListModels": list_models,
        "GetConversation": get_conversation,
    }


def agent_jobs_handlers(hub: ChatHub) -> Mapping[str, Handler]:
    """Every `AgentJobs` rpc, by rpc name, over the runner of the conversation the
    `CONVERSATION_HEADER` names."""

    async def wait_for_jobs(
        request: jobs_pb2.WaitForJobsRequest, ctx: RequestContext[Any, Any]
    ) -> jobs_pb2.WaitForJobsResponse:
        runner = _runner_of(hub, ctx)
        timeout_s = request.timeout_s if request.HasField("timeout_s") else MAX_WAIT_S
        if timeout_s > MAX_WAIT_S:
            raise ConnectError(Code.INVALID_ARGUMENT, f"timeout_s is at most {MAX_WAIT_S}")
        job_ids = list(request.job_ids)
        for job_id in job_ids:
            _job_or_refuse(runner, job_id)
        mode: WaitMode = "any" if request.mode == jobs_pb2.ANY else "all"
        waited = await runner.wait(job_ids, mode, timeout_s * runner.timeout_scale)
        return jobs_pb2.WaitForJobsResponse(
            jobs=[_job_result(job) for job in waited.jobs], timed_out=waited.timed_out
        )

    async def get_job(
        request: jobs_pb2.GetJobRequest, ctx: RequestContext[Any, Any]
    ) -> jobs_pb2.GetJobResponse:
        job = _job_or_refuse(_runner_of(hub, ctx), request.job_id)
        return jobs_pb2.GetJobResponse(job=_job_result(job))

    async def cancel_job(
        request: jobs_pb2.CancelJobRequest, ctx: RequestContext[Any, Any]
    ) -> jobs_pb2.CancelJobResponse:
        runner = _runner_of(hub, ctx)
        _job_or_refuse(runner, request.job_id)
        runner.cancel(request.job_id)
        settled = await runner.wait([request.job_id], "all", timeout_s=_CANCEL_SETTLE_S)
        return jobs_pb2.CancelJobResponse(job=_handle(settled.jobs[0]))

    async def list_jobs(
        _request: jobs_pb2.ListJobsRequest, ctx: RequestContext[Any, Any]
    ) -> jobs_pb2.ListJobsResponse:
        runner = _runner_of(hub, ctx)
        return jobs_pb2.ListJobsResponse(jobs=[_handle(job) for job in runner.jobs()])

    return {
        "WaitForJobs": wait_for_jobs,
        "GetJob": get_job,
        "CancelJob": cancel_job,
        "ListJobs": list_jobs,
    }


def turn_event_to_proto(
    event: TurnEvent, *, conversation_id: str, turn_id: str, seq: int
) -> chat_pb2.TurnEvent:
    """`event` as the `TurnEvent` at position `seq` of `turn_id` in the conversation."""
    if isinstance(event, TextDelta):
        return _event(conversation_id, turn_id, seq, text_delta=event.text)
    if isinstance(event, ToolCallStarted):
        return _event(conversation_id, turn_id, seq, tool_call_started=_started(event))
    if isinstance(event, ToolCallFinished):
        return _event(conversation_id, turn_id, seq, tool_call_finished=_finished(event))
    if isinstance(event, JobUpdate):
        return _event(conversation_id, turn_id, seq, job_update=_handle(event.job))
    if isinstance(event, SteerApplied):
        steer = chat_pb2.SteerApplied(
            text=event.text, detached_call_ids=list(event.detached_call_ids)
        )
        return _event(conversation_id, turn_id, seq, steer_applied=steer)
    if isinstance(event, SubagentMessage):
        message = chat_pb2.SubagentMessage(
            subagent_id=event.subagent_id, name=event.name, text=event.text
        )
        return _event(conversation_id, turn_id, seq, subagent_message=message)
    if isinstance(event, SubagentStatus):
        status = chat_pb2.SubagentStatus(
            subagent_id=event.subagent_id,
            name=event.name,
            job_id=event.job_id,
            status=_JOB_STATUS[event.state],
            detail=event.detail,
        )
        return _event(conversation_id, turn_id, seq, subagent_status=status)
    if isinstance(event, TurnFinished):
        finished = chat_pb2.TurnFinished(reason=_REASONS[event.reason])
        return _event(conversation_id, turn_id, seq, turn_finished=finished)
    if isinstance(event, TurnError):
        return _event(
            conversation_id, turn_id, seq, error=chat_pb2.TurnError(message=event.message)
        )
    assert_never(event)


def _event(conversation_id: str, turn_id: str, seq: int, **kind: Any) -> chat_pb2.TurnEvent:
    """A `TurnEvent` at `seq` of `turn_id` carrying the one oneof member `kind`."""
    return chat_pb2.TurnEvent(conversation_id=conversation_id, turn_id=turn_id, seq=seq, **kind)


def _started(event: ToolCallStarted) -> chat_pb2.ToolCallStarted:
    return chat_pb2.ToolCallStarted(
        call_id=event.call_id,
        tool=event.tool,
        arguments_json=json.dumps(dict(event.arguments), default=str),
        execution=_policy(event.execution),
    )


def _policy(policy: ExecutionPolicy) -> execution_pb2.ExecutionPolicy:
    return execution_pb2.ExecutionPolicy(
        mode=_MODES[policy.mode],
        timeout_s=policy.timeout_s,
        on_timeout=_TIMEOUTS[policy.on_timeout],
    )


def _finished(event: ToolCallFinished) -> chat_pb2.ToolCallFinished:
    outcome: ToolOutcome = event.outcome
    if isinstance(outcome, Completed):
        body, image = _split_image(outcome.result)
        finished = chat_pb2.ToolCallFinished(
            call_id=event.call_id,
            status=chat_pb2.ToolCallFinished.SUCCEEDED,
            result_json=json.dumps(body, default=str),
        )
        if image is not None:
            finished.image = image.data
            finished.media_type = image.media_type
        return finished
    if isinstance(outcome, Detached):
        return chat_pb2.ToolCallFinished(
            call_id=event.call_id,
            status=chat_pb2.ToolCallFinished.DETACHED,
            job=_handle(outcome.job),
        )
    assert isinstance(outcome, Failed)
    return chat_pb2.ToolCallFinished(
        call_id=event.call_id,
        status=chat_pb2.ToolCallFinished.FAILED,
        result_json=json.dumps({"error": outcome.error}, default=str),
    )


def _split_image(result: Mapping[str, object]) -> tuple[dict[str, object], ToolImage | None]:
    """The result without its image, and the image when the result carries one."""
    body = dict(result)
    image = body.get(IMAGE_KEY)
    if not isinstance(image, ToolImage):
        return body, None
    del body[IMAGE_KEY]
    return body, image


def _handle(job: Job) -> execution_pb2.JobHandle:
    """A job's handle: its identity, state, and the detail or error text when it has one."""
    return execution_pb2.JobHandle(
        job_id=job.job_id,
        tool=job.tool,
        status=_JOB_STATUS[job.state],
        detail=job.detail or job.error or "",
    )


def _job_result(job: Job) -> jobs_pb2.JobResult:
    """A job and, once it has succeeded, what its tool returned."""
    result = jobs_pb2.JobResult(job=_handle(job))
    if job.state is JobState.SUCCEEDED and job.result is not None:
        body, image = _split_image(job.result)
        result.result_json = json.dumps(body, default=str)
        if image is not None:
            result.image = image.data
            result.media_type = image.media_type
    return result


def _runner_of(hub: ChatHub, ctx: RequestContext[Any, Any]) -> JobRunner:
    """The job runner of the conversation the request's `CONVERSATION_HEADER` names."""
    conversation_id = ctx.request_headers.get(CONVERSATION_HEADER, "")
    if not conversation_id:
        raise ConnectError(
            Code.INVALID_ARGUMENT, f"the {CONVERSATION_HEADER} header names the conversation"
        )
    runner = hub.runner(conversation_id)
    if runner is None:
        raise ConnectError(Code.NOT_FOUND, f"no conversation {conversation_id}")
    return runner


def _job_or_refuse(runner: JobRunner, job_id: str) -> Job:
    job = runner.get(job_id)
    if job is None:
        raise ConnectError(Code.NOT_FOUND, f"no job {job_id}")
    return job


def _conversation_or_refuse(hub: ChatHub, conversation_id: str) -> Conversation:
    conversation = hub.get(conversation_id)
    if conversation is None:
        raise ConnectError(Code.NOT_FOUND, f"no conversation {conversation_id}")
    return conversation
