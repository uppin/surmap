"""The REST binding end to end, in process: ASGI → router → codec → connect-python app → response.

No server and no socket: the binding is driven with synthesized ASGI calls, and it dispatches into
a real connect-python application built over the fixture service.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any, cast

import pytest
from connectrpc.code import Code
from connectrpc.compat import google_protobuf_codecs
from connectrpc.errors import ConnectError
from connectrpc.method import IdempotencyLevel, MethodInfo
from connectrpc.request import RequestContext
from connectrpc.server import ConnectASGIApplication, Endpoint
from google.protobuf import message_factory, wrappers_pb2
from google.protobuf.descriptor import MethodDescriptor
from google.protobuf.message import Message

from surmap.rpc.http_rule.app import HttpRuleApplication
from surmap.rpc.http_rule.connect_invoker import ConnectAppInvoker
from surmap.rpc.http_rule.routes import HttpRuleRouter
from tests.rpc.unit.http_rule.fixture import fixture

SERVICE = fixture()
Kitchen = SERVICE.message("Kitchen")
Inner = SERVICE.message("Inner")
READ_MAX_BYTES = 4096


class _KitchenHandlers:
    calls: list[str]

    def __init__(self) -> None:
        self.calls = []

    async def GetKitchen(self, request: Any, ctx: RequestContext[Any, Any]) -> Message:  # noqa: N802
        self.calls.append("GetKitchen")
        probe = ctx.request_headers.get("x-probe")
        reply = cast(Any, Kitchen(name=request.name, i64=42))
        if probe:
            reply.maybe_name.CopyFrom(wrappers_pb2.StringValue(value=probe))
        return cast(Message, reply)

    async def CreateKitchen(self, request: Any, ctx: RequestContext[Any, Any]) -> Message:  # noqa: N802
        self.calls.append("CreateKitchen")
        return cast(Message, request)

    async def GetInnerOnly(self, request: Any, ctx: RequestContext[Any, Any]) -> Message:  # noqa: N802
        return Kitchen(name=request.name, inner=Inner(label=f"inner-of-{request.name}"))

    async def FailKitchen(self, request: Any, ctx: RequestContext[Any, Any]) -> Message:  # noqa: N802
        raise ConnectError(Code.NOT_FOUND, f"no kitchen {request.name}")

    async def StreamKitchens(  # noqa: N802
        self, request: Any, ctx: RequestContext[Any, Any]
    ) -> AsyncIterator[Message]:
        if request.name == "boom":
            raise ConnectError(Code.FAILED_PRECONDITION, "not before the first message")
        for index in range(3):
            yield Kitchen(name=f"{request.name}-{index}")

    async def StreamInners(  # noqa: N802
        self, request: Any, ctx: RequestContext[Any, Any]
    ) -> AsyncIterator[Message]:
        yield Kitchen(inner=Inner(label="first"))
        raise ConnectError(Code.UNAVAILABLE, "instance went away")


def _method_info(method: MethodDescriptor) -> MethodInfo[Any, Any]:
    return MethodInfo(
        name=method.name,
        service_name=method.containing_service.full_name,
        input=message_factory.GetMessageClass(method.input_type),
        output=message_factory.GetMessageClass(method.output_type),
        idempotency_level=IdempotencyLevel.UNKNOWN,
    )


class _FixtureApplication(ConnectASGIApplication[_KitchenHandlers]):
    def __init__(self, handlers: _KitchenHandlers) -> None:
        def endpoints(service: _KitchenHandlers) -> Mapping[str, Endpoint[Any, Any]]:
            table: dict[str, Endpoint[Any, Any]] = {}
            for method in SERVICE.service.methods:
                function = getattr(service, method.name, None)
                if function is None:
                    continue
                path = f"/{SERVICE.service.full_name}/{method.name}"
                info = _method_info(method)
                table[path] = (
                    Endpoint.server_stream(info, function)
                    if method.server_streaming
                    else Endpoint.unary(info, function)
                )
            return table

        # connectrpc types `endpoints` by its four concrete Endpoint subclasses; every value is one.
        super().__init__(
            service=handlers, endpoints=cast(Any, endpoints), codecs=google_protobuf_codecs()
        )

    @property
    def path(self) -> str:
        return f"/{SERVICE.service.full_name}"


@pytest.fixture
def handlers() -> _KitchenHandlers:
    return _KitchenHandlers()


@pytest.fixture
def invoker(handlers: _KitchenHandlers) -> ConnectAppInvoker:
    return ConnectAppInvoker({SERVICE.service.full_name: _FixtureApplication(handlers)})


@pytest.fixture
def app(invoker: ConnectAppInvoker) -> HttpRuleApplication:
    router = HttpRuleRouter.from_services([SERVICE.service])
    return HttpRuleApplication(router, invoker, read_max_bytes=READ_MAX_BYTES)


class _Response:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status, self.headers, self.body = status, headers, body

    def json(self) -> Any:
        return json.loads(self.body)

    def lines(self) -> list[Any]:
        return [json.loads(line) for line in self.body.splitlines()]


async def call(
    app: HttpRuleApplication,
    method: str,
    path: str,
    *,
    query: str = "",
    body: bytes | dict[str, Any] = b"",
    headers: Mapping[str, str] | None = None,
) -> _Response:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
    }
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": raw, "more_body": False}

    messages: list[Mapping[str, Any]] = []

    async def send(message: Mapping[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    response_headers = {k.decode(): v.decode() for k, v in start.get("headers", [])}
    body_bytes = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return _Response(start["status"], response_headers, body_bytes)


# --- unary ----------------------------------------------------------------------------------------


async def test_a_get_is_transcoded_into_the_method_and_back(app: HttpRuleApplication) -> None:
    response = await call(app, "GET", "/v1/kitchens/k1")
    assert response.status == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"name": "k1", "i64": "42"}


async def test_request_headers_reach_the_handler(app: HttpRuleApplication) -> None:
    response = await call(app, "GET", "/v1/kitchens/k1", headers={"x-probe": "carried"})
    assert response.json()["maybeName"] == "carried"


async def test_a_post_body_is_decoded_into_the_request(app: HttpRuleApplication) -> None:
    response = await call(app, "POST", "/v1/kitchens", body={"name": "k", "tags": ["a"]})
    assert response.status == 200
    assert response.json() == {"name": "k", "tags": ["a"]}


async def test_response_body_is_honoured_on_the_wire(app: HttpRuleApplication) -> None:
    response = await call(app, "GET", "/v1/kitchens/k1/inner")
    assert response.json() == {"label": "inner-of-k1"}


async def test_a_handler_error_becomes_its_http_status_and_status_body(
    app: HttpRuleApplication,
) -> None:
    response = await call(app, "GET", "/v1/failures/k9")
    assert response.status == 404
    assert response.json() == {"code": 5, "message": "no kitchen k9", "details": []}


async def test_an_invalid_request_is_refused_before_the_handler_runs(
    app: HttpRuleApplication, handlers: _KitchenHandlers
) -> None:
    response = await call(app, "POST", "/v1/kitchens", body={"nope": 1})
    assert response.status == 400
    assert response.json()["code"] == 3
    assert "nope" in response.json()["message"]
    assert handlers.calls == []


# --- streaming ------------------------------------------------------------------------------------


async def test_a_server_stream_is_ndjson_result_lines(app: HttpRuleApplication) -> None:
    response = await call(app, "POST", "/v1/kitchens:stream", body={"name": "k"})
    assert response.status == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.lines() == [
        {"result": {"name": "k-0"}},
        {"result": {"name": "k-1"}},
        {"result": {"name": "k-2"}},
    ]


async def test_a_stream_that_fails_after_its_first_message_ends_with_an_error_line(
    app: HttpRuleApplication,
) -> None:
    response = await call(app, "GET", "/v1/kitchens/k1/inners")
    assert response.status == 200
    assert response.lines() == [
        {"result": {"label": "first"}},
        {"error": {"code": 14, "message": "instance went away", "details": []}},
    ]


async def test_a_stream_that_fails_before_any_message_is_an_http_error(
    app: HttpRuleApplication,
) -> None:
    response = await call(app, "POST", "/v1/kitchens:stream", body={"name": "boom"})
    assert response.status == 400
    assert response.json() == {"code": 9, "message": "not before the first message", "details": []}


# --- routing and limits ---------------------------------------------------------------------------


async def test_an_unrouted_path_is_404(app: HttpRuleApplication) -> None:
    response = await call(app, "GET", "/v2/nothing")
    assert response.status == 404
    assert response.json()["code"] == 5


async def test_an_unannotated_method_is_unreachable_even_by_its_connect_path(
    app: HttpRuleApplication,
) -> None:
    response = await call(app, "POST", f"/{SERVICE.service.full_name}/Unannotated", body={})
    assert response.status == 404


async def test_a_wrong_verb_is_405_with_the_allowed_verbs(app: HttpRuleApplication) -> None:
    response = await call(app, "POST", "/v1/kitchens/k1")
    assert response.status == 405
    assert set(response.headers["allow"].split(", ")) == {"GET", "PUT", "DELETE"}


async def test_a_client_disconnect_during_the_body_does_not_invoke_the_handler(
    app: HttpRuleApplication, handlers: _KitchenHandlers
) -> None:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/kitchens",
        "raw_path": b"/v1/kitchens",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
    }
    calls = 0

    async def receive() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": b'{"name":', "more_body": True}
        return {"type": "http.disconnect"}

    messages: list[Mapping[str, Any]] = []

    async def send(message: Mapping[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    assert handlers.calls == []
    assert not any(m.get("type") == "http.response.start" for m in messages)


async def test_a_verb_route_matches_when_raw_path_is_absent(app: HttpRuleApplication) -> None:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/kitchens:stream",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
    }
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": b'{"name":"k"}', "more_body": False}

    messages: list[Mapping[str, Any]] = []

    async def send(message: Mapping[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    assert start["status"] == 200


async def test_a_body_over_the_limit_is_413(app: HttpRuleApplication) -> None:
    response = await call(app, "POST", "/v1/kitchens", body=b"{" + b" " * READ_MAX_BYTES + b"}")
    assert response.status == 413
    assert response.json()["code"] == 8


async def test_the_lifespan_protocol_is_acknowledged(app: HttpRuleApplication) -> None:
    received = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    sent: list[Mapping[str, Any]] = []

    async def receive() -> Mapping[str, Any]:
        return received.pop(0)

    async def send(message: Mapping[str, Any]) -> None:
        sent.append(message)

    await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
    assert [m["type"] for m in sent] == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


# --- the invoker alone ----------------------------------------------------------------------------


async def test_the_invoker_runs_a_unary_method_through_the_application(
    invoker: ConnectAppInvoker,
) -> None:
    method = SERVICE.service.methods_by_name["GetKitchen"]
    reply = await invoker.unary(method, Kitchen(name="k"), {})
    assert reply == Kitchen(name="k", i64=42)


async def test_the_invoker_streams_every_message(invoker: ConnectAppInvoker) -> None:
    method = SERVICE.service.methods_by_name["StreamKitchens"]
    names = [cast(Any, m).name async for m in invoker.server_stream(method, Kitchen(name="s"), {})]
    assert names == ["s-0", "s-1", "s-2"]


async def test_the_invoker_raises_the_handlers_connect_error(invoker: ConnectAppInvoker) -> None:
    method = SERVICE.service.methods_by_name["FailKitchen"]
    with pytest.raises(ConnectError) as error:
        await invoker.unary(method, Kitchen(name="k"), {})
    assert error.value.code == Code.NOT_FOUND
    assert "no kitchen k" in error.value.message


async def test_the_invoker_raises_a_mid_stream_error(invoker: ConnectAppInvoker) -> None:
    method = SERVICE.service.methods_by_name["StreamInners"]
    seen: list[str] = []
    with pytest.raises(ConnectError) as error:
        async for message in invoker.server_stream(method, Kitchen(), {}):
            seen.append(cast(Any, message).inner.label)
    assert seen == ["first"]
    assert error.value.code == Code.UNAVAILABLE
