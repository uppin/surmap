"""An in-memory descriptor pool for exercising HTTP rules without codegen or a server.

`Kitchen` carries every field kind the HttpRule spec allows or forbids in a path, a query or a
body; `Fixture` carries every rule shape. `build_service` makes a throwaway service for the cases a
router must refuse.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import cast

from google.api import annotations_pb2, http_pb2
from google.protobuf import (
    descriptor_pb2,
    descriptor_pool,
    duration_pb2,
    field_mask_pb2,
    message_factory,
    timestamp_pb2,
    wrappers_pb2,
)
from google.protobuf.descriptor import ServiceDescriptor
from google.protobuf.message import Message

F = descriptor_pb2.FieldDescriptorProto
PACKAGE = "test.httprule.v1"
_unique = itertools.count(1)

_DEPENDENCIES = (
    wrappers_pb2,
    timestamp_pb2,
    duration_pb2,
    field_mask_pb2,
    http_pb2,
    annotations_pb2,
)


def _pool() -> descriptor_pool.DescriptorPool:
    """The default pool: it already holds the well-known types, so fixture messages accept the
    same `wrappers_pb2` / `timestamp_pb2` instances the codec sees in production."""
    for module in _DEPENDENCIES:
        assert module.DESCRIPTOR.pool is descriptor_pool.Default()
    return descriptor_pool.Default()


def _field(
    message: descriptor_pb2.DescriptorProto,
    name: str,
    number: int,
    type_: int,
    *,
    type_name: str = "",
    repeated: bool = False,
    oneof_index: int | None = None,
) -> None:
    proto = message.field.add(
        name=name,
        number=number,
        type=type_,
        label=F.LABEL_REPEATED if repeated else F.LABEL_OPTIONAL,
    )
    if type_name:
        proto.type_name = type_name
    if oneof_index is not None:
        proto.oneof_index = oneof_index


def _kitchen_messages(file: descriptor_pb2.FileDescriptorProto, package: str) -> None:
    color = file.enum_type.add(name="Color")
    for name, number in (("COLOR_UNSPECIFIED", 0), ("RED", 1), ("GREEN", 2)):
        color.value.add(name=name, number=number)

    inner = file.message_type.add(name="Inner")
    _field(inner, "label", 1, F.TYPE_STRING)
    _field(inner, "count", 2, F.TYPE_INT32)
    _field(inner, "color", 3, F.TYPE_ENUM, type_name=f".{package}.Color")

    kitchen = file.message_type.add(name="Kitchen")
    kitchen.oneof_decl.add(name="choice")
    scalars = (
        ("name", F.TYPE_STRING),
        ("i32", F.TYPE_INT32),
        ("i64", F.TYPE_INT64),
        ("u32", F.TYPE_UINT32),
        ("u64", F.TYPE_UINT64),
        ("s32", F.TYPE_SINT32),
        ("f64", F.TYPE_FIXED64),
        ("flag", F.TYPE_BOOL),
        ("ratio", F.TYPE_DOUBLE),
        ("score", F.TYPE_FLOAT),
        ("blob", F.TYPE_BYTES),
    )
    numbers = itertools.count(1)
    for name, type_ in scalars:
        _field(kitchen, name, next(numbers), type_)
    _field(kitchen, "color", next(numbers), F.TYPE_ENUM, type_name=f".{package}.Color")
    _field(kitchen, "inner", next(numbers), F.TYPE_MESSAGE, type_name=f".{package}.Inner")
    _field(kitchen, "tags", next(numbers), F.TYPE_STRING, repeated=True)
    _field(kitchen, "ids", next(numbers), F.TYPE_INT64, repeated=True)
    _field(
        kitchen, "colors", next(numbers), F.TYPE_ENUM, type_name=f".{package}.Color", repeated=True
    )
    _field(
        kitchen,
        "inners",
        next(numbers),
        F.TYPE_MESSAGE,
        type_name=f".{package}.Inner",
        repeated=True,
    )

    labels_entry = kitchen.nested_type.add(name="LabelsEntry")
    labels_entry.options.map_entry = True
    _field(labels_entry, "key", 1, F.TYPE_STRING)
    _field(labels_entry, "value", 2, F.TYPE_STRING)
    _field(
        kitchen,
        "labels",
        next(numbers),
        F.TYPE_MESSAGE,
        type_name=f".{package}.Kitchen.LabelsEntry",
        repeated=True,
    )

    for name, wkt in (
        ("maybe_name", "google.protobuf.StringValue"),
        ("maybe_i64", "google.protobuf.Int64Value"),
        ("maybe_i32", "google.protobuf.Int32Value"),
        ("maybe_flag", "google.protobuf.BoolValue"),
        ("maybe_ratio", "google.protobuf.DoubleValue"),
        ("maybe_blob", "google.protobuf.BytesValue"),
        ("at", "google.protobuf.Timestamp"),
        ("ttl", "google.protobuf.Duration"),
        ("mask", "google.protobuf.FieldMask"),
    ):
        _field(kitchen, name, next(numbers), F.TYPE_MESSAGE, type_name=f".{wkt}")
    _field(kitchen, "choice_text", next(numbers), F.TYPE_STRING, oneof_index=0)
    _field(kitchen, "choice_number", next(numbers), F.TYPE_INT32, oneof_index=0)
    _field(kitchen, "snake_case_field", next(numbers), F.TYPE_STRING)
    _field(kitchen, "resource_name", next(numbers), F.TYPE_STRING)


@dataclass(frozen=True)
class Rule:
    """One method of a fixture service and its HTTP rule (None for an unannotated method)."""

    name: str
    rule: http_pb2.HttpRule | None
    request: str = "Kitchen"
    response: str = "Kitchen"
    client_streaming: bool = False
    server_streaming: bool = False


def rule(**fields: object) -> http_pb2.HttpRule:
    """`rule(get="/v1/x/{name}", body="*")`, `custom=("SEARCH", "/v1/x")`, `additional=[...]`."""
    built = http_pb2.HttpRule()
    for key, value in fields.items():
        if key == "custom":
            kind, path = cast(tuple[str, str], value)
            built.custom.kind = kind
            built.custom.path = path
        elif key == "additional":
            built.additional_bindings.extend(cast(list[http_pb2.HttpRule], value))
        else:
            setattr(built, key, value)
    return built


@dataclass
class BuiltService:
    service: ServiceDescriptor
    pool: descriptor_pool.DescriptorPool
    package: str
    classes: dict[str, type[Message]] = field(default_factory=dict)

    def message(self, name: str) -> type[Message]:
        if name not in self.classes:
            descriptor = self.pool.FindMessageTypeByName(f"{self.package}.{name}")
            self.classes[name] = message_factory.GetMessageClass(descriptor)
        return self.classes[name]


def build_service(rules: list[Rule], *, service_name: str = "Fixture") -> BuiltService:
    """A fresh pool holding `Kitchen`/`Inner` and one service with `rules`."""
    package = f"{PACKAGE}.p{next(_unique)}"
    file = descriptor_pb2.FileDescriptorProto(
        name=f"{package.replace('.', '/')}/fixture.proto",
        package=package,
        syntax="proto3",
        dependency=[module.DESCRIPTOR.name for module in _DEPENDENCIES],
    )
    _kitchen_messages(file, package)
    service = file.service.add(name=service_name)
    for spec in rules:
        method = service.method.add(
            name=spec.name,
            input_type=f".{package}.{spec.request}",
            output_type=f".{package}.{spec.response}",
            client_streaming=spec.client_streaming,
            server_streaming=spec.server_streaming,
        )
        if spec.rule is not None:
            method.options.Extensions[annotations_pb2.http].CopyFrom(spec.rule)
    pool = _pool()
    pool.Add(file)
    return BuiltService(
        service=pool.FindServiceByName(f"{package}.{service_name}"), pool=pool, package=package
    )


FIXTURE_RULES: list[Rule] = [
    Rule("GetKitchen", rule(get="/v1/kitchens/{name}")),
    Rule("GetByInner", rule(get="/v1/inner/{inner.label}/kitchen")),
    Rule("CreateKitchen", rule(post="/v1/kitchens")),
    Rule("PutKitchen", rule(put="/v1/kitchens/{name}")),
    Rule("UpdateInner", rule(patch="/v1/kitchens/{name}/inner")),
    Rule("UpdateTags", rule(post="/v1/kitchens/{name}/tags")),
    Rule("DeleteKitchen", rule(delete="/v1/kitchens/{name}")),
    Rule("SearchKitchens", rule(custom=("SEARCH", "/v1/kitchens"))),
    Rule("CancelKitchen", rule(post="/v1/kitchens/{name}:cancel")),
    Rule("GetResource", rule(get="/v1/{resource_name=projects/*/kitchens/*}")),
    Rule("GetFile", rule(get="/v1/files/{name=**}")),
    Rule("GetInnerOnly", rule(get="/v1/kitchens/{name}/inner", response_body="inner")),
    Rule("GetTagsOnly", rule(get="/v1/kitchens/{name}/tags", response_body="tags")),
    Rule(
        "GetAliased",
        rule(get="/v1/kitchens/{name}/alias", additional=[rule(get="/v1/aliases/{name}")]),
    ),
    Rule("ListKitchens", rule(get="/v1/kitchens")),
    Rule("StreamKitchens", rule(post="/v1/kitchens:stream"), server_streaming=True),
    Rule(
        "StreamInners",
        rule(get="/v1/kitchens/{name}/inners", response_body="inner"),
        server_streaming=True,
    ),
    Rule("FailKitchen", rule(get="/v1/failures/{name}")),
    Rule("Unannotated", None),
    Rule("Chat", None, client_streaming=True, server_streaming=True),
]


def fixture() -> BuiltService:
    return build_service(FIXTURE_RULES)
