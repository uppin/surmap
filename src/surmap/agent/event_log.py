"""The agent's event log: one greppable `event=<name> key=value …` line per thing that happened.

Logger `surmap.agent.events`, INFO; `python -m surmap.agent` writes it to stderr, which Modal
keeps (`modal app logs surmap-agent | grep event=turn_finished`). Values with spaces, quotes or
`=` are double-quoted. Lines:

- `turn_started conversation turn model trigger=user|job`
- `tool_started conversation turn tool call`
- `tool_finished conversation turn tool call status=succeeded|failed|detached duration_ms [error]`
- `turn_finished conversation turn reason text_chars tools duration_ms`
- `turn_error conversation turn error`
- `auth_signin result=ok|refused` — never the code (`surmap.agent.server.routes`)
- `auth_refused surface=rpc|http target` (`routes`, `app`)
- `station action=start|stop|idle_stop state duration_ms [error]` (`surmap.agent.tools.station*`)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from surmap.agent.runtime.events import (
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnError,
    TurnFinished,
)
from surmap.agent.runtime.events import TurnEvent as RuntimeEvent
from surmap.agent.runtime.jobs import Detached, Failed

EVENT_LOGGER = "surmap.agent.events"

_log = logging.getLogger(EVENT_LOGGER)
_NEEDS_QUOTES = (" ", '"', "=", "\t", "\n")


def logfmt(event: str, **fields: object) -> str:
    """`event=<event>` then each field as `key=value`, in the order given."""
    parts = [f"event={event}"]
    for key, value in fields.items():
        text = str(value).lower() if isinstance(value, bool) else str(value)
        if not text or any(mark in text for mark in _NEEDS_QUOTES):
            text = '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'
        parts.append(f"{key}={text}")
    return " ".join(parts)


def log_event(event: str, **fields: object) -> None:
    """Write one event line at INFO."""
    _log.info(logfmt(event, **fields))


@dataclass
class _Turn:
    started: float
    text_chars: int = 0
    tools: int = 0
    calls: dict[str, float] = field(default_factory=dict)


@dataclass
class TurnLog:
    """Follows one conversation's turns from their runtime events and logs each one."""

    conversation_id: str
    model_id: str
    clock: Callable[[], float] = time.monotonic
    _turns: dict[str, _Turn] = field(default_factory=dict)

    def user_message(self, turn_id: str) -> None:
        self._start(turn_id, "user")

    def observe(self, turn_id: str, event: RuntimeEvent) -> None:
        turn = self._turns.get(turn_id) or self._start(turn_id, "job")
        ids = {"conversation": self.conversation_id, "turn": turn_id}
        if isinstance(event, TextDelta):
            turn.text_chars += len(event.text)
        elif isinstance(event, ToolCallStarted):
            turn.tools += 1
            turn.calls[event.call_id] = self.clock()
            log_event("tool_started", **ids, tool=event.tool, call=event.call_id)
        elif isinstance(event, ToolCallFinished):
            began = turn.calls.pop(event.call_id, self.clock())
            status, error = _outcome(event)
            extra = {"error": error} if error else {}
            log_event(
                "tool_finished",
                **ids,
                tool=event.tool,
                call=event.call_id,
                status=status,
                duration_ms=self._ms_since(began),
                **extra,
            )
        elif isinstance(event, TurnFinished):
            del self._turns[turn_id]
            log_event(
                "turn_finished",
                **ids,
                reason=event.reason,
                text_chars=turn.text_chars,
                tools=turn.tools,
                duration_ms=self._ms_since(turn.started),
            )
        elif isinstance(event, TurnError):
            del self._turns[turn_id]
            log_event("turn_error", **ids, error=event.message)

    def _start(self, turn_id: str, trigger: str) -> _Turn:
        turn = _Turn(started=self.clock())
        self._turns[turn_id] = turn
        log_event(
            "turn_started",
            conversation=self.conversation_id,
            turn=turn_id,
            model=self.model_id,
            trigger=trigger,
        )
        return turn

    def _ms_since(self, began: float) -> int:
        return int((self.clock() - began) * 1000)


def _outcome(event: ToolCallFinished) -> tuple[str, str]:
    outcome = event.outcome
    if isinstance(outcome, Failed):
        return "failed", outcome.error
    if isinstance(outcome, Detached):
        return "detached", ""
    return "succeeded", ""
