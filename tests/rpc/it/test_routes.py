"""Health and metrics — the routes every server shape serves."""

from __future__ import annotations

from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.in_memory import InMemoryHost
from surmap.rpc.http import HttpResponse
from surmap.rpc.routes import (
    HEALTH_PATH,
    METRICS_CONTENT_TYPE,
    METRICS_PATH,
    health_routes,
    metrics_route,
)
from surmap.rpc.testkit import aio_http_stub


async def test_health_is_alive_until_the_server_drains() -> None:
    draining = False
    host = InMemoryHost(ServerDescription(http_routes=health_routes(lambda: draining)), None)

    alive = await host.http("GET", HEALTH_PATH)
    draining = True
    drained = await host.http("GET", HEALTH_PATH)

    assert (alive.status, alive.body) == (200, b"Alive")
    assert drained.status == 503


async def test_metrics_render_in_the_prometheus_content_type() -> None:
    host = InMemoryHost(ServerDescription(http_routes=(metrics_route(lambda: "gauge 1\n"),)), None)

    response = await host.http("GET", METRICS_PATH)

    assert response.status == 200
    assert response.body == b"gauge 1\n"
    assert response.headers["content-type"] == METRICS_CONTENT_TYPE


async def test_a_third_party_stub_serves_only_its_routes() -> None:
    async def models(_request: object) -> HttpResponse:
        return HttpResponse(
            status=200, body=b'{"models":[]}', headers={"content-type": "application/json"}
        )

    host = InMemoryHost(aio_http_stub({("GET", "/v1/models"): models}), None)

    assert (await host.http("GET", "/v1/models")).body == b'{"models":[]}'
    assert (await host.http("GET", "/v1/other")).status == 404
