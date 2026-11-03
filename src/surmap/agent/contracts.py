"""Model-facing tool contracts, built from the `surmap.agent.v1` proto descriptors.

Every tool rpc (`SurveyTools`, `AgentJobs`) becomes one `ToolContract`: its snake_case name,
its leading proto comment as the description, the JSON Schema (2020-12) of its request message
with an optional `execution` argument added, and the `default_execution` its method option
declares. The rpc and field comments come from the checked-in descriptor set
(`surmap/agent/proto/agent_descriptor_set.binpb`), compiled with source info.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from google.protobuf.descriptor import ServiceDescriptor

__all__ = [
    "ExecutionMode",
    "ExecutionPolicy",
    "OnTimeout",
    "ToolContract",
    "resolve_execution",
    "tool_contracts",
]


class ExecutionMode(Enum):
    """Whether a tool call blocks the turn or returns a job handle at once."""

    SYNC = "SYNC"
    ASYNC = "ASYNC"


class OnTimeout(Enum):
    """What a SYNC call does when its timeout passes before it finishes."""

    FAIL = "FAIL"
    DETACH = "DETACH"


@dataclass(frozen=True)
class ExecutionPolicy:
    """How one tool call runs: its mode, how long it may block, and what happens after that."""

    mode: ExecutionMode
    timeout_s: int
    on_timeout: OnTimeout


@dataclass(frozen=True)
class ToolContract:
    """What a model binds for one tool rpc."""

    name: str
    """The snake_case tool name, e.g. `"run_demo"`."""
    service: str
    """The proto service's full name, e.g. `"surmap.agent.v1.SurveyTools"`."""
    method: str
    """The rpc's name, e.g. `"RunDemo"`."""
    description: str
    """The rpc's leading comment."""
    input_schema: Mapping[str, object]
    """JSON Schema 2020-12 of the request, with an optional `execution` property."""
    default_execution: ExecutionPolicy
    """The rpc's `default_execution` method option."""


def tool_contracts(service_descriptor: ServiceDescriptor) -> tuple[ToolContract, ...]:
    """One contract per rpc of a tool service, in declaration order.

    Raises `ValueError` naming any rpc that declares no `default_execution`: a service whose
    rpcs are not tools (such as `ChatService`) has no contracts.
    """
    raise NotImplementedError  # TODO(pr-1): implement


def resolve_execution(contract: ToolContract, arguments: Mapping[str, object]) -> ExecutionPolicy:
    """The execution a call with these model arguments runs with.

    The contract's default, with any field the arguments' `execution` object names replaced by
    its value. Raises `ValueError` for an `execution` value the schema does not allow.
    """
    raise NotImplementedError  # TODO(pr-1): implement
