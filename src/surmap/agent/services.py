"""`ServiceModule`s for the survey agent's three services.

Handlers are supplied by rpc name in connect-python's shapes (`(request, ctx)` for unary and
server-streaming rpcs). Every rpc without a handler answers `UNIMPLEMENTED`, so a module mounts
before all of its handlers exist; a handler named for an rpc the service does not have is a
mount-time `CompositionError`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from surmap.rpc.description import ServiceModule

__all__ = ["Handler", "agent_jobs_module", "chat_service_module", "survey_tools_module"]

Handler = Callable[..., Any]


def survey_tools_module(handlers: Mapping[str, Handler]) -> ServiceModule[Any]:
    """The module mounting `surmap.agent.v1.SurveyTools`."""
    raise NotImplementedError  # TODO(pr-1): implement


def agent_jobs_module(handlers: Mapping[str, Handler]) -> ServiceModule[Any]:
    """The module mounting `surmap.agent.v1.AgentJobs`."""
    raise NotImplementedError  # TODO(pr-1): implement


def chat_service_module(handlers: Mapping[str, Handler]) -> ServiceModule[Any]:
    """The module mounting `surmap.agent.v1.ChatService`."""
    raise NotImplementedError  # TODO(pr-1): implement
