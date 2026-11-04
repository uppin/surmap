"""The tools a conversation binds: the `SurveyTools` handlers and the job tools, over its runner.

A `SurveyTools` handler speaks protos in connect-python's `(request, ctx)` shape. Bound as a
tool, a call's JSON arguments (without `execution`) decode into the rpc's request message, the
handler runs with no request context, and its response comes back as the JSON object
`json_format.MessageToDict` makes of it (proto field names, defaults included). A `bytes` field
named `image` does not go into the JSON: it comes back as a `ToolImage` under `IMAGE_KEY`, which
the model reads as a one-line placeholder and the chat stream carries as image bytes. A
`ConnectError` from the handler, or arguments the request message cannot hold, fail the call.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from google.protobuf import descriptor_pool
from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessageClass

from surmap.agent.contracts import ToolContract, resolve_execution
from surmap.agent.runtime.jobs import JobRunner, ToolHandler
from surmap.agent.runtime.tools import BoundTool, ExecutionResolver, bind_contract_tool, job_tools
from surmap.agent.services import Handler

__all__ = ["IMAGE_KEY", "ToolImage", "agent_tools"]

IMAGE_KEY = "image"
"""Where a bound tool's result carries the image its response returned."""

_SURVEY_SERVICE = "surmap.agent.v1.SurveyTools"
_MAP_SERVICE = "surmap.agent.v1.MapTools"
_JOBS_SERVICE = "surmap.agent.v1.AgentJobs"
_SIMULATION_SERVICE = "surmap.agent.v1.SimulationTools"
_FLEET_SERVICE = "surmap.agent.v1.FleetTools"
_HANDLER_SERVICES = (_SURVEY_SERVICE, _MAP_SERVICE, _SIMULATION_SERVICE, _FLEET_SERVICE)


@dataclass(frozen=True)
class ToolImage:
    """An image a tool returned, kept out of the JSON the model reads."""

    data: bytes
    media_type: str

    def __str__(self) -> str:
        """What the model reads in place of the bytes, e.g.
        `"<image/jpeg, 48213 bytes, shown to the user>"`."""
        return f"<{self.media_type}, {len(self.data)} bytes, shown to the user>"


def agent_tools(
    contracts: Sequence[ToolContract],
    handlers: Mapping[str, Handler],
    runner: JobRunner,
    *,
    resolve: ExecutionResolver = resolve_execution,
) -> tuple[BoundTool, ...]:
    """Every contract as a tool over `runner`.

    `SurveyTools`, `MapTools`, `SimulationTools` and `FleetTools` contracts are bound to
    `handlers` by rpc name; `AgentJobs` contracts become the four job tools
    (`surmap.agent.runtime.tools.job_tools`). Raises `ValueError` for a contract no handler
    serves.
    """
    bound: list[BoundTool] = []
    for contract in contracts:
        if contract.service not in _HANDLER_SERVICES:
            continue
        handler = handlers.get(contract.method)
        if handler is None:
            raise ValueError(f"no handler serves the {contract.service} rpc {contract.method}")
        tool_handler = _tool_handler(handler, _request_type(contract))
        bound.append(bind_contract_tool(contract, tool_handler, runner, resolve=resolve))
    jobs = [contract for contract in contracts if contract.service == _JOBS_SERVICE]
    bound.extend(job_tools(runner, jobs, resolve=resolve))
    return tuple(bound)


def _request_type(contract: ToolContract) -> type[Message]:
    """The request message class of the rpc a contract names."""
    service = descriptor_pool.Default().FindServiceByName(contract.service)
    return GetMessageClass(service.FindMethodByName(contract.method).input_type)


def _tool_handler(handler: Handler, request_type: type[Message]) -> ToolHandler:
    """The JSON-in, JSON-out tool handler over one connect-shape `SurveyTools` handler."""

    async def call(arguments: Mapping[str, object]) -> Mapping[str, object]:
        request = ParseDict(dict(arguments), request_type())
        response = await handler(request, None)
        return _response_json(response)

    return call


def _response_json(response: Message) -> dict[str, object]:
    """The response as a JSON object; a non-empty `image` field becomes a `ToolImage`."""
    body: dict[str, object] = MessageToDict(
        response, preserving_proto_field_name=True, always_print_fields_with_no_presence=True
    )
    image_field = response.DESCRIPTOR.fields_by_name.get(IMAGE_KEY)
    if image_field is None or image_field.type != FieldDescriptor.TYPE_BYTES:
        return body
    body.pop(IMAGE_KEY, None)
    image = getattr(response, IMAGE_KEY)
    if image:
        body[IMAGE_KEY] = ToolImage(bytes(image), str(getattr(response, "media_type", "")))
    return body
