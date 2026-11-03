"""What a stuck WebSocket shows: the calls each peer has open, and a trace of every socket and call.

With `SURMAP_SOCKET_RPC_TRACE=1` the server route, the survey client and every call log their
lifecycle (`surmap.rpc.socket_rpc.trace`); `describe_open_socket_calls()` lists what every live
peer is still waiting on — what a hang dump prints.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from google.protobuf.wrappers_pb2 import StringValue

from surmap.rpc.compose import Brick
from surmap.rpc.description import ServerDescription, ServiceModule
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.socket_rpc import describe_open_socket_calls
from surmap.survey.cm5_main import build_description
from surmap.survey.ws_client import SurveyConnection
from tests.rpc.echo_service import echo_service
from tests.rpc.it.test_connect_websocket import CONNECT_PATH, _dialed, _method

TRACE_LOGGER = "surmap.rpc.socket_rpc.trace"


async def test_a_call_waiting_on_the_server_is_listed_as_open_with_its_method() -> None:
    # Given a server whose Unary never answers
    service = echo_service()
    never = asyncio.Event()

    async def hang(request: StringValue, ctx: object) -> StringValue:
        await never.wait()
        return request

    async def each(requests: AsyncIterator[StringValue], ctx: object) -> AsyncIterator[StringValue]:
        async for request in requests:
            yield request

    async def first(request: StringValue, ctx: object) -> AsyncIterator[StringValue]:
        yield request

    methods: dict[str, Callable[..., Any]] = {
        "Unary": hang,
        "ServerStream": first,
        "ClientStream": hang,
        "Bidi": each,
    }
    description: ServerDescription[None] = ServerDescription(
        services=(ServiceModule(service, lambda _c: [Brick(methods=methods)]),),
        connect_websocket_path=CONNECT_PATH,
    )
    host = HypercornHost(description, None)
    port = (await host.start()).public
    try:
        async with _dialed(f"ws://127.0.0.1:{port}{CONNECT_PATH}") as peer:
            # When a call is in flight
            call = asyncio.create_task(peer.call_unary(_method(service, "Unary"), StringValue()))
            await asyncio.sleep(0.2)
            open_now = describe_open_socket_calls()
            client_side = peer.open_calls()
            call.cancel()
    finally:
        never.set()
        await host.stop()

    # Then both ends list it: the dialer's outgoing call and the acceptor's incoming one
    assert [(c.direction, c.method) for c in client_side] == [("out", f"{service.full_name}/Unary")]
    assert any("in " in line and f"{service.full_name}/Unary" in line for line in open_now)
    assert any("out " in line and f"{service.full_name}/Unary" in line for line in open_now)


async def test_tracing_logs_each_socket_and_call_from_open_to_close(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Given tracing on and a CM5 server
    monkeypatch.setenv("SURMAP_SOCKET_RPC_TRACE", "1")
    caplog.set_level(logging.INFO, logger=TRACE_LOGGER)
    host = HypercornHost(build_description(use_stereo=False), None)
    port = (await host.start()).public
    try:
        # When a survey client connects, asks for capabilities and leaves
        async with SurveyConnection.open(f"127.0.0.1:{port}") as connection:
            await connection.capabilities("Cm5SurveyService")
    finally:
        await host.stop()

    # Then the trace names each step on both ends, and the call's method
    events = [record.getMessage().split(" ")[2] for record in caplog.records]
    for event in (
        "ws.client.open",
        "ws.server.accepted",
        "ws.client.greeted",
        "call.out.open",
        "call.in.open",
        "call.in.end",
        "call.out.end",
        "ws.client.closed",
        "ws.server.closed",
    ):
        assert event in events, f"{event} missing from {events}"
    assert any(
        "surmap.survey.v1.Cm5SurveyService/GetCapabilities" in record.getMessage()
        for record in caplog.records
        if " call.out.end " in record.getMessage()
    )


async def test_a_refused_token_is_traced_on_both_ends(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Given tracing on and a token-guarded server
    monkeypatch.setenv("SURMAP_SOCKET_RPC_TRACE", "1")
    caplog.set_level(logging.INFO, logger=TRACE_LOGGER)
    host = HypercornHost(build_description(use_stereo=False), None, auth_token="secret")
    port = (await host.start()).public
    try:
        # When a client connects without it
        with pytest.raises(PermissionError):
            async with SurveyConnection.open(f"127.0.0.1:{port}"):
                pass
    finally:
        await host.stop()

    # Then the server traced the refusal and the client traced being refused
    messages = [record.getMessage() for record in caplog.records]
    assert any(" ws.server.refused " in message for message in messages)
    assert any(" ws.client.refused " in message for message in messages)


async def test_with_tracing_off_nothing_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    # Given tracing off (the default)
    caplog.set_level(logging.DEBUG, logger=TRACE_LOGGER)
    host = HypercornHost(build_description(use_stereo=False), None)
    port = (await host.start()).public
    try:
        # When a client connects and calls
        async with SurveyConnection.open(f"127.0.0.1:{port}") as connection:
            await connection.capabilities("Cm5SurveyService")
    finally:
        await host.stop()

    # Then the trace logger stayed quiet
    assert [r for r in caplog.records if r.name == TRACE_LOGGER] == []
