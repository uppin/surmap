"""A brick that records every call and answers from a script."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from google.protobuf.descriptor import MethodDescriptor, ServiceDescriptor
from google.protobuf.message import Message

from surmap.rpc.compose import Brick

__all__ = ["RecordedCall", "RecordingBrick"]


@dataclass(frozen=True)
class RecordedCall:
    method: str
    request: Message
    headers: Mapping[str, str]


def _is_unary(method: MethodDescriptor) -> bool:
    return not method.client_streaming and not method.server_streaming


def _is_server_stream(method: MethodDescriptor) -> bool:
    return method.server_streaming and not method.client_streaming


def _is_client_stream(method: MethodDescriptor) -> bool:
    return method.client_streaming and not method.server_streaming


def _is_bidi(method: MethodDescriptor) -> bool:
    return bool(method.client_streaming and method.server_streaming)


class RecordingBrick:
    """Claims every method of `service` and answers each with `replies[method]`."""

    def __init__(self, service: ServiceDescriptor, replies: Mapping[str, Message]) -> None:
        self._service = service
        self._replies = dict(replies)
        self.calls: list[RecordedCall] = []

    def _record(self, method_name: str, request: Message, ctx: Any) -> None:
        self.calls.append(RecordedCall(method_name, request, dict(ctx.request_headers.items())))

    @property
    def brick(self) -> Brick:
        methods: dict[str, Any] = {}
        for method in self._service.methods:
            name = method.name

            if _is_unary(method):

                async def unary_handler(
                    request: Message, ctx: Any, *, method_name: str = name
                ) -> Message:
                    self._record(method_name, request, ctx)
                    return self._replies[method_name]

                methods[name] = unary_handler
                continue

            if _is_server_stream(method):

                async def server_stream_handler(
                    request: Message,
                    ctx: Any,
                    *,
                    method_name: str = name,
                ) -> AsyncIterator[Message]:
                    self._record(method_name, request, ctx)
                    yield self._replies[method_name]

                methods[name] = server_stream_handler
                continue

            if _is_client_stream(method):

                async def client_stream_handler(
                    requests: AsyncIterator[Message],
                    ctx: Any,
                    *,
                    method_name: str = name,
                ) -> Message:
                    first = await anext(requests)
                    self._record(method_name, first, ctx)
                    async for _rest in requests:
                        pass
                    return self._replies[method_name]

                methods[name] = client_stream_handler
                continue

            if _is_bidi(method):

                async def bidi_handler(
                    requests: AsyncIterator[Message],
                    ctx: Any,
                    *,
                    method_name: str = name,
                ) -> AsyncIterator[Message]:
                    async for request in requests:
                        self._record(method_name, request, ctx)
                        yield self._replies[method_name]

                methods[name] = bidi_handler

        return Brick(methods=methods)
