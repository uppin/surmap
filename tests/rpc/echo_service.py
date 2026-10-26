"""A test service in an in-memory descriptor pool: one method of each kind, over StringValue."""

from __future__ import annotations

import itertools

from google.protobuf import descriptor_pb2, descriptor_pool, wrappers_pb2
from google.protobuf.descriptor import ServiceDescriptor

_unique = itertools.count(1)
_STRING = ".google.protobuf.StringValue"


def echo_service(name: str = "Echo", *, extra_methods: tuple[str, ...] = ()) -> ServiceDescriptor:
    """`Unary`, `ServerStream`, `ClientStream`, `Bidi` (+ unary `extra_methods`), fresh package."""
    package = f"test.kit.p{next(_unique)}"
    file = descriptor_pb2.FileDescriptorProto(
        name=f"{package.replace('.', '/')}/echo.proto",
        package=package,
        syntax="proto3",
        dependency=[wrappers_pb2.DESCRIPTOR.name],
    )
    service = file.service.add(name=name)
    kinds = {
        "Unary": (False, False),
        "ServerStream": (False, True),
        "ClientStream": (True, False),
        "Bidi": (True, True),
    }
    for method, (client, server) in kinds.items():
        service.method.add(
            name=method,
            input_type=_STRING,
            output_type=_STRING,
            client_streaming=client,
            server_streaming=server,
        )
    for method in extra_methods:
        service.method.add(name=method, input_type=_STRING, output_type=_STRING)
    pool = descriptor_pool.Default()
    pool.Add(file)
    return pool.FindServiceByName(f"{package}.{name}")
