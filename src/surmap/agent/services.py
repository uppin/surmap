"""`ServiceModule`s for the survey agent's three services.

Handlers are supplied by rpc name in connect-python's shapes (`(request, ctx)` for unary and
server-streaming rpcs). Every rpc without a handler answers `UNIMPLEMENTED`, so a module mounts
before all of its handlers exist; a handler named for an rpc the service does not have is a
mount-time `CompositionError`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from google.protobuf.descriptor import MethodDescriptor, ServiceDescriptor

from surmap.agent.proto import chat_pb2, jobs_pb2, survey_tools_pb2
from surmap.rpc.compose import Brick
from surmap.rpc.description import ServiceModule

__all__ = ["Handler", "agent_jobs_module", "chat_service_module", "survey_tools_module"]

Handler = Callable[..., Any]


def survey_tools_module(handlers: Mapping[str, Handler]) -> ServiceModule[Any]:
    """The module mounting `surmap.agent.v1.SurveyTools`."""
    return _module(survey_tools_pb2.DESCRIPTOR.services_by_name["SurveyTools"], handlers)


def agent_jobs_module(handlers: Mapping[str, Handler]) -> ServiceModule[Any]:
    """The module mounting `surmap.agent.v1.AgentJobs`."""
    return _module(jobs_pb2.DESCRIPTOR.services_by_name["AgentJobs"], handlers)


def chat_service_module(handlers: Mapping[str, Handler]) -> ServiceModule[Any]:
    """The module mounting `surmap.agent.v1.ChatService`."""
    return _module(chat_pb2.DESCRIPTOR.services_by_name["ChatService"], handlers)


def _module(service: ServiceDescriptor, handlers: Mapping[str, Handler]) -> ServiceModule[Any]:
    """Every rpc of `service`, served by its supplied handler or else `UNIMPLEMENTED`.

    A supplied name the service lacks is kept, so mounting refuses it as an unknown rpc.
    """
    methods: dict[str, Handler] = {
        method.name: _unimplemented(method) for method in service.methods
    }
    methods.update(handlers)
    return ServiceModule(descriptor=service, bricks=lambda _context: (Brick(methods=methods),))


def _unimplemented(method: MethodDescriptor) -> Handler:
    message = f"{method.full_name} is not implemented yet"
    if method.server_streaming:

        async def stream(_request: object, _ctx: object) -> AsyncIterator[None]:
            await _refuse(message)
            yield

        return stream

    async def unary(_request: object, _ctx: object) -> None:
        await _refuse(message)

    return unary


async def _refuse(message: str) -> None:
    """Answers UNIMPLEMENTED. Awaited by the default handlers, so they never return."""
    raise ConnectError(Code.UNIMPLEMENTED, message)
