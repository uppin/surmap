"""Services composed from bricks, with exact method coverage."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from connectrpc.compat import google_protobuf_codecs
from connectrpc.method import IdempotencyLevel, MethodInfo
from connectrpc.server import ConnectASGIApplication, Endpoint
from google.protobuf.descriptor import MethodDescriptor, ServiceDescriptor
from google.protobuf.message_factory import GetMessageClass

__all__ = ["Brick", "CompositionError", "compose_service"]


@dataclass(frozen=True)
class Brick:
    """Some of a service's methods, by name, and the handlers that serve them.

    A handler takes `(request, ctx)` for unary and server-streaming methods, and
    `(requests, ctx)` for client-streaming and bidi methods — connect-python's own shapes.
    """

    methods: Mapping[str, Callable[..., Any]]


class CompositionError(ValueError):
    """The bricks do not cover the service exactly once."""

    def __init__(
        self,
        service: str,
        *,
        unimplemented: tuple[str, ...] = (),
        duplicated: tuple[str, ...] = (),
        unknown: tuple[str, ...] = (),
    ) -> None:
        self.service = service
        self.unimplemented = unimplemented
        self.duplicated = duplicated
        self.unknown = unknown
        super().__init__(service)

    def __str__(self) -> str:
        parts = [self.service]
        parts.extend(self.unimplemented)
        parts.extend(self.duplicated)
        parts.extend(self.unknown)
        return " ".join(parts)


def _is_unary(method: MethodDescriptor) -> bool:
    return not method.client_streaming and not method.server_streaming


def _is_server_stream(method: MethodDescriptor) -> bool:
    return method.server_streaming and not method.client_streaming


def _is_client_stream(method: MethodDescriptor) -> bool:
    return method.client_streaming and not method.server_streaming


def _is_bidi_stream(method: MethodDescriptor) -> bool:
    return bool(method.client_streaming and method.server_streaming)


def _method_info(service: ServiceDescriptor, method: MethodDescriptor) -> MethodInfo[Any, Any]:
    return MethodInfo(
        name=method.name,
        service_name=service.full_name,
        input=GetMessageClass(method.input_type),
        output=GetMessageClass(method.output_type),
        idempotency_level=IdempotencyLevel.UNKNOWN,
    )


def _validate_coverage(
    service: ServiceDescriptor, bricks: tuple[Brick, ...]
) -> dict[str, Callable[..., Any]]:
    service_methods = {method.name for method in service.methods}
    counts: Counter[str] = Counter()
    handlers: dict[str, Callable[..., Any]] = {}
    unknown: list[str] = []

    for brick in bricks:
        for name, handler in brick.methods.items():
            counts[name] += 1
            if name not in service_methods:
                unknown.append(name)
            else:
                handlers[name] = handler

    unimplemented = sorted(service_methods - set(handlers.keys()))
    duplicated = sorted(name for name, count in counts.items() if count > 1)
    unknown_sorted = sorted(set(unknown))

    if unimplemented or duplicated or unknown_sorted:
        raise CompositionError(
            service.full_name,
            unimplemented=tuple(unimplemented),
            duplicated=tuple(duplicated),
            unknown=tuple(unknown_sorted),
        )
    return handlers


def compose_service(service: ServiceDescriptor, *bricks: Brick) -> ConnectASGIApplication[Any]:
    """A connect-python application serving every method of `service` from `bricks`.

    Endpoints are derived from the descriptor, so all four method kinds are served without being
    listed. Raises `CompositionError` naming every method no brick claims, every method claimed
    twice, and every claimed name the service does not have.
    """
    handlers = _validate_coverage(service, bricks)
    endpoints: dict[str, Endpoint[Any, Any]] = {}
    for method in service.methods:
        path = f"/{service.full_name}/{method.name}"
        handler = handlers[method.name]
        info = _method_info(service, method)
        if _is_unary(method):
            endpoints[path] = Endpoint.unary(info, handler)
        elif _is_server_stream(method):
            endpoints[path] = Endpoint.server_stream(info, handler)
        elif _is_client_stream(method):
            endpoints[path] = Endpoint.client_stream(info, handler)
        elif _is_bidi_stream(method):
            endpoints[path] = Endpoint.bidi_stream(info, handler)

    class _ComposedService:
        pass

    class _App(ConnectASGIApplication[_ComposedService]):
        def __init__(self) -> None:
            super().__init__(
                service=_ComposedService(),
                endpoints=lambda _instance: cast("Any", endpoints),
                codecs=google_protobuf_codecs(),
            )

        @property
        def path(self) -> str:
            return f"/{service.full_name}"

    return cast("ConnectASGIApplication[Any]", _App())
