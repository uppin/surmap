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

from collections.abc import Mapping

from surmap.agent.proto import chat_pb2
from surmap.agent.runtime.events import TurnEvent
from surmap.agent.server.hub import ChatHub
from surmap.agent.services import Handler

__all__ = ["CONVERSATION_HEADER", "agent_jobs_handlers", "chat_handlers", "turn_event_to_proto"]

CONVERSATION_HEADER = "surmap-conversation-id"
"""The request header naming the conversation an `AgentJobs` rpc reads the jobs of."""


def chat_handlers(hub: ChatHub) -> Mapping[str, Handler]:
    """Every `ChatService` rpc, by rpc name, as a `(request, ctx)` handler over `hub`."""
    raise NotImplementedError  # TODO(pr-8): implement


def agent_jobs_handlers(hub: ChatHub) -> Mapping[str, Handler]:
    """Every `AgentJobs` rpc, by rpc name, over the runner of the conversation the
    `CONVERSATION_HEADER` names."""
    raise NotImplementedError  # TODO(pr-8): implement


def turn_event_to_proto(
    event: TurnEvent, *, conversation_id: str, turn_id: str, seq: int
) -> chat_pb2.TurnEvent:
    """`event` as the `TurnEvent` at position `seq` of `turn_id` in the conversation."""
    raise NotImplementedError  # TODO(pr-8): implement
