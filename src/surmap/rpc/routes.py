"""The routes every server shape serves: health and metrics."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from surmap.rpc.description import HttpRoute
from surmap.rpc.http import HttpRequest, HttpResponse

__all__ = [
    "HEALTH_PATH",
    "METRICS_CONTENT_TYPE",
    "METRICS_PATH",
    "health_routes",
    "metrics_route",
]

HEALTH_PATH = "/health/is_alive"
METRICS_PATH = "/metrics"
METRICS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def health_routes(is_draining: Callable[[], bool]) -> tuple[HttpRoute[Any], ...]:
    """`GET /health/is_alive` → 200 `Alive`, or 503 while the server drains."""

    async def is_alive(_request: HttpRequest) -> HttpResponse:
        if is_draining():
            return HttpResponse(status=503, body=b"Draining")
        return HttpResponse(status=200, body=b"Alive")

    return (HttpRoute("GET", HEALTH_PATH, lambda _context: is_alive),)


def metrics_route(render: Callable[[], str]) -> HttpRoute[Any]:
    """`GET /metrics` → `render()` in the Prometheus text exposition format."""

    async def metrics(_request: HttpRequest) -> HttpResponse:
        return HttpResponse(
            status=200,
            body=render().encode(),
            headers={"content-type": METRICS_CONTENT_TYPE},
        )

    return HttpRoute("GET", METRICS_PATH, lambda _context: metrics)
