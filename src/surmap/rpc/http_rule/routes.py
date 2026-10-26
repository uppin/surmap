"""The route table: one binding per HTTP rule, from service descriptors — annotated methods only.

A method with no `google.api.http` rule gets no binding, so it has no REST route at all: the rule
is the exposure decision as well as the mapping. Rules that cannot be served — a bad template, a
field that does not exist or cannot be bound where the rule puts it, two rules matching the same
requests, a client-streaming method — are refused when the table is built, not when a request
arrives.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property

from google.api import annotations_pb2, http_pb2
from google.protobuf import message_factory
from google.protobuf.descriptor import (
    Descriptor,
    FieldDescriptor,
    MethodDescriptor,
    ServiceDescriptor,
)
from google.protobuf.message import Message

from surmap.rpc.http_rule.path_template import (
    PathTemplate,
    TemplateSyntaxError,
)

__all__ = ["HttpBinding", "HttpRuleConfigError", "HttpRuleRouter", "RouteMatch", "is_scalar_leaf"]

_WRAPPER_TYPES = frozenset(
    f"google.protobuf.{name}"
    for name in (
        "DoubleValue",
        "FloatValue",
        "Int64Value",
        "UInt64Value",
        "Int32Value",
        "UInt32Value",
        "BoolValue",
        "StringValue",
        "BytesValue",
    )
)


class HttpRuleConfigError(ValueError):
    """A rule that cannot be served: bad template, unknown field, conflict, unsupported kind."""


def is_scalar_leaf(field: FieldDescriptor) -> bool:
    """A singular field one path or query value can carry: a scalar, an enum or a wrapper."""
    if field.is_repeated:
        return False
    if field.type == FieldDescriptor.TYPE_MESSAGE:
        return field.message_type is not None and field.message_type.full_name in _WRAPPER_TYPES
    return True


@dataclass(frozen=True)
class HttpBinding:
    """One HTTP rule (or additional binding) of one method."""

    method: MethodDescriptor
    http_method: str
    template: PathTemplate
    body: str
    response_body: str

    @cached_property
    def request_class(self) -> type[Message]:
        return message_factory.GetMessageClass(self.method.input_type)

    @cached_property
    def response_class(self) -> type[Message]:
        return message_factory.GetMessageClass(self.method.output_type)

    @property
    def server_streaming(self) -> bool:
        return bool(self.method.server_streaming)


@dataclass(frozen=True)
class RouteMatch:
    binding: HttpBinding
    path_params: dict[str, str]


class HttpRuleRouter:
    def __init__(self, bindings: tuple[HttpBinding, ...]) -> None:
        self.bindings = bindings

    @classmethod
    def from_services(cls, services: Iterable[ServiceDescriptor]) -> HttpRuleRouter:
        """Every rule of every method; raises `HttpRuleConfigError` for one it cannot serve."""
        bindings: list[HttpBinding] = []
        claimed: dict[tuple[str, object], str] = {}
        for service in services:
            for method in service.methods:
                options = method.GetOptions()
                if not options.HasExtension(annotations_pb2.http):
                    continue
                rule = options.Extensions[annotations_pb2.http]
                if method.client_streaming:
                    raise HttpRuleConfigError(
                        f"{method.full_name}: a client-streaming method cannot have an HTTP rule"
                    )
                for each in _rules_of(method, rule):
                    binding = _binding(method, each)
                    key = (binding.http_method, binding.template.shape())
                    if key in claimed:
                        raise HttpRuleConfigError(
                            f"{method.full_name}: {binding.http_method} "
                            f"{binding.template.template} conflicts with {claimed[key]}"
                        )
                    claimed[key] = method.full_name
                    bindings.append(binding)
        return cls(tuple(bindings))

    def match(self, http_method: str, path: str) -> RouteMatch | None:
        best: RouteMatch | None = None
        best_rank: tuple[int, ...] = ()
        for binding in self.bindings:
            if binding.http_method != http_method:
                continue
            params = binding.template.match(path)
            if params is None:
                continue
            rank = binding.template.specificity()
            if best is None or rank > best_rank:
                best, best_rank = RouteMatch(binding=binding, path_params=params), rank
        return best

    def allowed_methods(self, path: str) -> frozenset[str]:
        """The HTTP methods some rule accepts for `path` — the `Allow` header of a 405."""
        return frozenset(
            binding.http_method
            for binding in self.bindings
            if binding.template.match(path) is not None
        )


def _rules_of(method: MethodDescriptor, rule: http_pb2.HttpRule) -> list[http_pb2.HttpRule]:
    for additional in rule.additional_bindings:
        if additional.additional_bindings:
            raise HttpRuleConfigError(
                f"{method.full_name}: an additional binding cannot have additional bindings"
            )
    return [rule, *rule.additional_bindings]


def _binding(method: MethodDescriptor, rule: http_pb2.HttpRule) -> HttpBinding:
    if rule.body:
        raise HttpRuleConfigError(
            f"{method.full_name}: google.api.http body {rule.body!r} is not supported "
            "(An HTTP rule may declare path and verb only; request fields then bind "
            "from the JSON body "
            "at runtime)"
        )
    pattern = rule.WhichOneof("pattern")
    if pattern is None:
        raise HttpRuleConfigError(f"{method.full_name}: the HTTP rule names no method or path")
    if pattern == "custom":
        http_method, path = rule.custom.kind.upper(), rule.custom.path
    else:
        http_method, path = pattern.upper(), getattr(rule, pattern)
    try:
        template = PathTemplate.parse(path)
    except TemplateSyntaxError as error:
        raise HttpRuleConfigError(f"{method.full_name}: {error}") from error

    request = method.input_type
    for variable in template.variables:
        field = _resolve(method, request, variable.field_path)
        if not is_scalar_leaf(field):
            raise HttpRuleConfigError(
                f"{method.full_name}: path variable {variable.dotted!r} "
                "must be a scalar, enum or wrapper field"
            )

    if rule.response_body and rule.response_body not in method.output_type.fields_by_name:
        raise HttpRuleConfigError(
            f"{method.full_name}: response_body {rule.response_body!r} is not a top-level field "
            f"of {method.output_type.full_name}"
        )
    return HttpBinding(
        method=method,
        http_method=http_method,
        template=template,
        body=rule.body,
        response_body=rule.response_body,
    )


def _resolve(
    method: MethodDescriptor, message: Descriptor, path: tuple[str, ...]
) -> FieldDescriptor:
    current = message
    field: FieldDescriptor | None = None
    for position, part in enumerate(path):
        field = current.fields_by_name.get(part)
        dotted = ".".join(path)
        if field is None:
            raise HttpRuleConfigError(
                f"{method.full_name}: path variable {dotted!r} — "
                f"{current.full_name} has no field {part!r}"
            )
        if position < len(path) - 1:
            if (
                field.type != FieldDescriptor.TYPE_MESSAGE
                or field.is_repeated
                or field.message_type is None
                or field.message_type.full_name in _WRAPPER_TYPES
            ):
                raise HttpRuleConfigError(
                    f"{method.full_name}: path variable {dotted!r} passes through {part!r}, "
                    f"which is not a singular message"
                )
            if field.message_type is None:
                raise HttpRuleConfigError(
                    f"{method.full_name}: path variable {dotted!r} passes through {part!r}, "
                    f"which is not a singular message"
                )
            current = field.message_type
    assert field is not None
    return field
