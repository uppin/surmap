"""Model-facing tool contracts, built from the `surmap.agent.v1` proto descriptors.

Every tool rpc (`SurveyTools`, `AgentJobs`) becomes one `ToolContract`: its snake_case name,
its leading proto comment as the description, the JSON Schema (2020-12) of its request message
with optional `execution` and `output` arguments added, and the `default_execution` its method
option declares. The rpc and field comments come from the checked-in descriptor set
(`surmap/agent/proto/agent_descriptor_set.binpb`), compiled with source info.
"""

from __future__ import annotations

import functools
import importlib.resources
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from google.protobuf.descriptor import (
    Descriptor,
    EnumDescriptor,
    FieldDescriptor,
    MethodDescriptor,
    ServiceDescriptor,
)
from google.protobuf.descriptor_pb2 import DescriptorProto, FileDescriptorSet

from surmap.agent.proto import execution_pb2

__all__ = [
    "ExecutionMode",
    "ExecutionPolicy",
    "OnTimeout",
    "ToolContract",
    "resolve_execution",
    "resolve_output",
    "tool_contracts",
    "tool_input_schema",
]

E = TypeVar("E", bound=Enum)

_DESCRIPTOR_SET = "agent_descriptor_set.binpb"
_JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_EXECUTION_DESCRIPTION = (
    "How this call runs, when it should differ from the tool's default: give any of mode, "
    "timeout_s and on_timeout, and the others keep their default."
)
_OVERRIDABLE = ("mode", "timeout_s", "on_timeout")
_OUTPUT_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "description": (
        "Where this call's result goes. Leave it out for the result inline; a result too big "
        "for the conversation is saved to a file anyway, and you get its path instead."
    ),
    "properties": {
        "to_file": {
            "type": "boolean",
            "description": (
                "Save the result to a file and return only its path, size and a preview; read "
                "or search it with read_file and grep_files."
            ),
        }
    },
    "additionalProperties": False,
}
_UINT32_MAX = 2**32 - 1
_INTEGER_TYPES = frozenset(
    {
        FieldDescriptor.TYPE_INT32,
        FieldDescriptor.TYPE_INT64,
        FieldDescriptor.TYPE_UINT32,
        FieldDescriptor.TYPE_UINT64,
        FieldDescriptor.TYPE_SINT32,
        FieldDescriptor.TYPE_SINT64,
        FieldDescriptor.TYPE_FIXED32,
        FieldDescriptor.TYPE_FIXED64,
        FieldDescriptor.TYPE_SFIXED32,
        FieldDescriptor.TYPE_SFIXED64,
    }
)
_NUMBER_TYPES = frozenset({FieldDescriptor.TYPE_DOUBLE, FieldDescriptor.TYPE_FLOAT})


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
    not_tools = [m.name for m in service_descriptor.methods if not _declares_default(m)]
    if not_tools:
        raise ValueError(
            f"{service_descriptor.full_name} declares no default_execution on "
            f"{', '.join(not_tools)}, so these rpcs are not tools"
        )
    return tuple(_contract(service_descriptor, method) for method in service_descriptor.methods)


def resolve_execution(contract: ToolContract, arguments: Mapping[str, object]) -> ExecutionPolicy:
    """The execution a call with these model arguments runs with.

    The contract's default, with any field the arguments' `execution` object names replaced by
    its value. Raises `ValueError` for an `execution` value the schema does not allow.
    """
    default = contract.default_execution
    if "execution" not in arguments:
        return default
    override = arguments["execution"]
    if not isinstance(override, Mapping):
        raise ValueError(f"execution must be an object, not {override!r}")
    unknown = [str(name) for name in override if name not in _OVERRIDABLE]
    if unknown:
        raise ValueError(f"execution has no field {', '.join(unknown)}")
    mode, timeout_s, on_timeout = default.mode, default.timeout_s, default.on_timeout
    if "mode" in override:
        mode = _choice(ExecutionMode, override["mode"], "mode")
    if "timeout_s" in override:
        timeout_s = _timeout(override["timeout_s"])
    if "on_timeout" in override:
        on_timeout = _choice(OnTimeout, override["on_timeout"], "on_timeout")
    return ExecutionPolicy(mode=mode, timeout_s=timeout_s, on_timeout=on_timeout)


def resolve_output(arguments: Mapping[str, object]) -> bool:
    """Whether the call's `output` argument asks for its result as a file.

    Raises `ValueError` for an `output` value the schema does not allow.
    """
    if "output" not in arguments:
        return False
    output = arguments["output"]
    if not isinstance(output, Mapping):
        raise ValueError(f"output must be an object, not {output!r}")
    unknown = [str(name) for name in output if name != "to_file"]
    if unknown:
        raise ValueError(f"output has no field {', '.join(unknown)}")
    to_file = output.get("to_file", False)
    if not isinstance(to_file, bool):
        raise ValueError(f"output.to_file {to_file!r} is not true or false")
    return to_file


def _contract(service: ServiceDescriptor, method: MethodDescriptor) -> ToolContract:
    description = _leading_comment(method.full_name)
    if not description:
        raise ValueError(f"{method.full_name} has no leading comment to describe the tool")
    return ToolContract(
        name=_snake_case(method.name),
        service=service.full_name,
        method=method.name,
        description=description,
        input_schema=_tool_schema(method.input_type),
        default_execution=_default_execution(method),
    )


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _declares_default(method: MethodDescriptor) -> bool:
    return method.GetOptions().HasExtension(execution_pb2.default_execution)


def _default_execution(method: MethodDescriptor) -> ExecutionPolicy:
    declared = method.GetOptions().Extensions[execution_pb2.default_execution]
    mode = execution_pb2.ExecutionMode.Name(declared.mode)
    on_timeout = execution_pb2.OnTimeout.Name(declared.on_timeout)
    if mode not in ExecutionMode.__members__ or on_timeout not in OnTimeout.__members__:
        raise ValueError(f"{method.full_name} declares an unspecified default_execution")
    return ExecutionPolicy(
        mode=ExecutionMode[mode],
        timeout_s=declared.timeout_s,
        on_timeout=OnTimeout[on_timeout],
    )


def _choice(enum_cls: type[E], value: object, field: str) -> E:
    if not isinstance(value, str) or value not in enum_cls.__members__:
        choices = ", ".join(enum_cls.__members__)
        raise ValueError(f"execution.{field} {value!r} is not one of {choices}")
    return enum_cls[value]


def _timeout(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _UINT32_MAX:
        raise ValueError(f"execution.timeout_s {value!r} is not a whole number of seconds")
    return value


def tool_input_schema(
    properties: Mapping[str, object], *, required: Sequence[str] = ()
) -> dict[str, object]:
    """A tool's argument schema: `properties` plus the optional `execution` and `output`
    arguments every tool carries, as `tool_contracts` builds it — for tools no proto declares
    (skills, subagents, files)."""
    all_properties = dict(properties)
    all_properties["execution"] = _execution_schema()
    all_properties["output"] = dict(_OUTPUT_SCHEMA)
    return {"$schema": _JSON_SCHEMA_DIALECT, **_object_schema(all_properties, list(required))}


def _tool_schema(request: Descriptor) -> dict[str, object]:
    """The request's JSON Schema with the optional `execution` argument added."""
    properties, required = _properties(request)
    return tool_input_schema(properties, required=required)


def _execution_schema() -> dict[str, object]:
    """The `ExecutionPolicy` message as an optional object: a call may override any part."""
    schema = _message_schema(execution_pb2.DESCRIPTOR.message_types_by_name["ExecutionPolicy"])
    schema.pop("required", None)
    schema["description"] = _EXECUTION_DESCRIPTION
    return schema


def _message_schema(message: Descriptor) -> dict[str, object]:
    return _object_schema(*_properties(message))


def _properties(message: Descriptor) -> tuple[dict[str, object], list[str]]:
    properties: dict[str, object] = {}
    required: list[str] = []
    for field in message.fields:
        properties[field.name] = _field_schema(field)
        # A singular proto3 field without presence always has a value (its zero if unset), so the
        # model must give one.
        if not field.is_repeated and not field.has_presence:
            required.append(field.name)
    return properties, required


def _object_schema(properties: dict[str, object], required: list[str]) -> dict[str, object]:
    schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _field_schema(field: FieldDescriptor) -> dict[str, object]:
    schema = _element_schema(field)
    if field.is_repeated:
        schema = {"type": "array", "items": schema}
    comment = _leading_comment(field.full_name)
    if comment:
        schema["description"] = comment
    return schema


def _element_schema(field: FieldDescriptor) -> dict[str, object]:
    if field.message_type is not None:
        return _message_schema(field.message_type)
    if field.enum_type is not None:
        return _enum_schema(field.enum_type)
    return _scalar_schema(field.type)


def _enum_schema(enum: EnumDescriptor) -> dict[str, object]:
    # The *_UNSPECIFIED zero value means "not set", so it is not offered as a choice.
    names = [value.name for value in enum.values if not value.name.endswith("_UNSPECIFIED")]
    return {"type": "string", "enum": names}


def _scalar_schema(kind: int) -> dict[str, object]:
    if kind == FieldDescriptor.TYPE_STRING:
        return {"type": "string"}
    if kind == FieldDescriptor.TYPE_BOOL:
        return {"type": "boolean"}
    if kind == FieldDescriptor.TYPE_BYTES:
        return {"type": "string", "contentEncoding": "base64"}
    if kind in _INTEGER_TYPES:
        return {"type": "integer"}
    if kind in _NUMBER_TYPES:
        return {"type": "number"}
    raise ValueError(f"no JSON Schema for proto field type {kind}")


def _leading_comment(full_name: str) -> str:
    return _leading_comments().get(full_name, "")


@functools.cache
def _leading_comments() -> Mapping[str, str]:
    """The leading comment of every rpc and message field in the descriptor set, by full name.

    The generated modules carry no source info, so the comments are read from the checked-in
    descriptor set, which is compiled with it.
    """
    data = importlib.resources.files("surmap.agent.proto").joinpath(_DESCRIPTOR_SET).read_bytes()
    comments: dict[str, str] = {}
    for file in FileDescriptorSet.FromString(data).file:
        by_path = {
            tuple(location.path): _one_line(location.leading_comments)
            for location in file.source_code_info.location
            if location.leading_comments.strip()
        }
        for s_index, service in enumerate(file.service):
            for m_index, method in enumerate(service.method):
                path = (6, s_index, 2, m_index)
                _keep(comments, f"{file.package}.{service.name}.{method.name}", by_path, path)
        for index, message in enumerate(file.message_type):
            _message_comments(
                f"{file.package}.{message.name}", (4, index), message, by_path, comments
            )
    return comments


def _message_comments(
    full_name: str,
    path: tuple[int, ...],
    message: DescriptorProto,
    by_path: Mapping[tuple[int, ...], str],
    comments: dict[str, str],
) -> None:
    for index, field in enumerate(message.field):
        _keep(comments, f"{full_name}.{field.name}", by_path, (*path, 2, index))
    for index, nested in enumerate(message.nested_type):
        _message_comments(
            f"{full_name}.{nested.name}", (*path, 3, index), nested, by_path, comments
        )


def _keep(
    comments: dict[str, str],
    full_name: str,
    by_path: Mapping[tuple[int, ...], str],
    path: tuple[int, ...],
) -> None:
    if path in by_path:
        comments[full_name] = by_path[path]


def _one_line(comment: str) -> str:
    """The comment's text on one line: its lines stripped and joined by spaces."""
    return " ".join(line.strip() for line in comment.splitlines() if line.strip())
