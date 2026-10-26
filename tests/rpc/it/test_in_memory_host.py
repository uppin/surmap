"""The in-memory host serves a composed service — every method kind, errors, headers, closeables."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from google.protobuf.wrappers_pb2 import StringValue

from surmap.rpc.asgi import call_unary
from surmap.rpc.compose import Brick, compose_service
from surmap.rpc.description import HttpRoute, ServerDescription, ServiceModule
from surmap.rpc.hosts.in_memory import InMemoryHost
from surmap.rpc.http import HttpRequest, HttpResponse
from surmap.rpc.testkit import RecordingBrick
from tests.rpc.echo_service import echo_service


class _Echo:
    async def unary(self, request: StringValue, ctx: Any) -> StringValue:
        if request.value == "fail":
            raise ConnectError(Code.FAILED_PRECONDITION, "refused fail")
        probe = ctx.request_headers.get("x-probe")
        return StringValue(value=f"echo:{request.value}" + (f"+{probe}" if probe else ""))

    async def server_stream(self, request: StringValue, ctx: Any) -> AsyncIterator[StringValue]:
        for index in range(3):
            yield StringValue(value=f"{request.value}:{index}")

    async def client_stream(self, requests: AsyncIterator[StringValue], ctx: Any) -> StringValue:
        return StringValue(value="+".join([r.value async for r in requests]))

    async def bidi(
        self, requests: AsyncIterator[StringValue], ctx: Any
    ) -> AsyncIterator[StringValue]:
        async for request in requests:
            yield StringValue(value=f"echo:{request.value}")


def _bricks(echo: _Echo) -> list[Brick]:
    return [
        Brick(methods={"Unary": echo.unary, "ServerStream": echo.server_stream}),
        Brick(methods={"ClientStream": echo.client_stream, "Bidi": echo.bidi}),
    ]


async def _values(stream: AsyncIterator[StringValue]) -> list[str]:
    return [message.value async for message in stream]


async def _requests(*values: str) -> AsyncIterator[StringValue]:
    for value in values:
        yield StringValue(value=value)


class _Closer:
    def __init__(self, name: str, log: list[str]) -> None:
        self._name, self._log = name, log

    async def close(self) -> None:
        self._log.append(self._name)


@pytest.fixture
def service() -> Any:
    return echo_service()


@pytest.fixture
def host(service: Any) -> InMemoryHost[_Echo]:
    description = ServerDescription(services=(ServiceModule(service, _bricks),))
    return InMemoryHost(description, _Echo())


async def test_a_unary_call_is_served(host: InMemoryHost[_Echo], service: Any) -> None:
    reply = await host.client(service).unary("Unary", StringValue(value="hi"))
    assert reply == StringValue(value="echo:hi")


async def test_request_headers_reach_the_handler(host: InMemoryHost[_Echo], service: Any) -> None:
    reply = await host.client(service).unary(
        "Unary", StringValue(value="hi"), {"x-probe": "carried"}
    )
    assert cast(StringValue, reply).value == "echo:hi+carried"


async def test_a_server_stream_yields_every_message_in_order(
    host: InMemoryHost[_Echo], service: Any
) -> None:
    stream = cast(
        AsyncIterator[StringValue],
        host.client(service).server_stream("ServerStream", StringValue(value="s")),
    )
    values = await _values(stream)
    assert values == ["s:0", "s:1", "s:2"]


async def test_a_client_stream_collects_every_request(
    host: InMemoryHost[_Echo], service: Any
) -> None:
    reply = await host.client(service).client_stream("ClientStream", _requests("a", "b", "c"))
    assert cast(StringValue, reply).value == "a+b+c"


async def test_a_bidi_stream_echoes_in_order(host: InMemoryHost[_Echo], service: Any) -> None:
    stream = cast(
        AsyncIterator[StringValue], host.client(service).bidi("Bidi", _requests("x", "y"))
    )
    values = await _values(stream)
    assert values == ["echo:x", "echo:y"]


async def test_a_handler_error_keeps_its_code(host: InMemoryHost[_Echo], service: Any) -> None:
    with pytest.raises(ConnectError) as error:
        await host.client(service).unary("Unary", StringValue(value="fail"))
    assert error.value.code == Code.FAILED_PRECONDITION
    assert "refused fail" in error.value.message


async def test_a_service_the_host_does_not_mount_is_refused(host: InMemoryHost[_Echo]) -> None:
    with pytest.raises(KeyError):
        host.client(echo_service("Other"))


async def test_the_asgi_driver_calls_a_composed_application_directly(service: Any) -> None:
    app = compose_service(service, *_bricks(_Echo()))
    reply = await call_unary(app, service.methods_by_name["Unary"], StringValue(value="direct"))
    assert reply == StringValue(value="echo:direct")


async def test_bricks_are_built_from_the_context_only_when_mounted(service: Any) -> None:
    built: list[str] = []

    def bricks(context: str) -> list[Brick]:
        built.append(context)
        return _bricks(_Echo())

    description = ServerDescription(services=(ServiceModule(service, bricks),))
    assert built == []
    InMemoryHost(description, "the-context")
    assert built == ["the-context"]


async def test_an_http_route_is_dispatched_with_its_request() -> None:
    seen: list[HttpRequest] = []

    async def handle(request: HttpRequest) -> HttpResponse:
        seen.append(request)
        return HttpResponse(status=201, body=b"made", headers={"content-type": "text/plain"})

    description: ServerDescription[None] = ServerDescription(
        http_routes=(HttpRoute("POST", "/things", lambda _c: handle),)
    )
    host = InMemoryHost(description, None)

    response = await host.http("POST", "/things", query="a=1", body=b"x", headers={"x-h": "v"})

    assert (response.status, response.body) == (201, b"made")
    assert (seen[0].method, seen[0].path, seen[0].query, seen[0].body) == (
        "POST",
        "/things",
        "a=1",
        b"x",
    )
    assert seen[0].headers["x-h"] == "v"


async def test_an_unrouted_path_is_404_and_a_wrong_verb_is_405() -> None:
    async def handle(request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200)

    host = InMemoryHost(
        ServerDescription(http_routes=(HttpRoute("GET", "/x", lambda _c: handle),)), None
    )
    assert (await host.http("GET", "/nothing")).status == 404
    assert (await host.http("POST", "/x")).status == 405


async def test_http_routes_fall_back_to_a_method_wildcard_path() -> None:
    async def catch_all(request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=418, body=request.path.encode())

    host = InMemoryHost(
        ServerDescription(
            http_routes=(
                HttpRoute("GET", "/known", lambda _c: catch_all),
                HttpRoute("POST", "*", lambda _c: catch_all),
            )
        ),
        None,
    )
    assert (await host.http("POST", "/tuning/jobs")).body == b"/tuning/jobs"
    assert (await host.http("GET", "/unknown")).status == 404


async def test_closeables_close_once_in_reverse_order() -> None:
    log: list[str] = []
    closers = [_Closer("first", log), _Closer("second", log)]
    host = InMemoryHost(ServerDescription(closeables=lambda _c: closers), None)

    await host.close()
    await host.close()

    assert log == ["second", "first"]


async def test_a_recording_brick_records_calls_and_answers_from_its_script(service: Any) -> None:
    recording = RecordingBrick(service, {"Unary": StringValue(value="scripted")})
    description: ServerDescription[None] = ServerDescription(
        services=(ServiceModule(service, lambda _c: [recording.brick]),)
    )
    host = InMemoryHost(description, None)

    reply = await host.client(service).unary("Unary", StringValue(value="asked"), {"x-who": "test"})

    assert reply == StringValue(value="scripted")
    assert [(c.method, c.request, c.headers.get("x-who")) for c in recording.calls] == [
        ("Unary", StringValue(value="asked"), "test")
    ]
