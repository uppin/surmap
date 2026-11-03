"""The per-turn LangGraph graph.

```text
          ┌──────── pending (steers, job notices) drained here
START ─► model ──(tool calls)──► tools ──► model … ──(no calls)──► END
            └─(round cap | repeated identical failures)──► cut_off ──► END
```

Tool calls of one model batch run one at a time through their `BoundTool`. `cut_off` answers
every unanswered call with a "Not run" tool result. There is no checkpointer: the session seeds
the history and appends what the turn adds.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph

from surmap.agent.runtime.events import FinishReason
from surmap.agent.runtime.tools import BoundTool

__all__ = [
    "MAX_ROUNDS_ENV",
    "PendingDrain",
    "TurnCaps",
    "TurnGraph",
    "TurnState",
    "build_turn_graph",
    "turn_input",
]

MAX_ROUNDS_ENV = "SURMAP_AGENT_MAX_ROUNDS"

PendingDrain = Callable[[], Sequence[BaseMessage]]
"""Takes the messages queued since the last call (steers, job notices), oldest first."""


@dataclass(frozen=True)
class TurnCaps:
    """Where a runaway turn is cut off."""

    max_rounds: int = 30
    """Tool rounds a turn may run; the model call asking for more is answered "Not run"."""
    max_identical_failures: int = 3
    """Failures of the same tool with the same arguments before the turn is cut off."""

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> TurnCaps:
        """The defaults, with `max_rounds` from `SURMAP_AGENT_MAX_ROUNDS` when it is set.

        Raises `ValueError` for a value that is not a positive integer.
        """
        raise NotImplementedError  # TODO(pr-4): implement


class TurnState(TypedDict):
    """The graph's state for one turn."""

    messages: Annotated[list[BaseMessage], operator.add]
    """The conversation so far plus what this turn added."""
    rounds: int
    """Tool rounds run so far in this turn."""
    finish_reason: FinishReason | None
    """Set by the node that ends the turn."""


TurnGraph = CompiledStateGraph[TurnState, None, TurnState, TurnState]


def turn_input(messages: Sequence[BaseMessage]) -> TurnState:
    """The state a turn starts from: the history to answer, no rounds run, no reason yet."""
    return {"messages": list(messages), "rounds": 0, "finish_reason": None}


def build_turn_graph(
    model: BaseChatModel,
    tools: Sequence[BoundTool],
    pending: PendingDrain,
    caps: TurnCaps,
) -> TurnGraph:
    """Compile the turn graph for `model` bound to `tools`."""
    raise NotImplementedError  # TODO(pr-4): implement
