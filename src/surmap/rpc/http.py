"""The HTTP vocabulary routes speak — independent of the host that carries them."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

__all__ = ["HttpHandler", "HttpRequest", "HttpResponse"]


@dataclass(frozen=True)
class HttpRequest:
    method: str
    path: str
    query: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)


HttpHandler = Callable[[HttpRequest], Awaitable[HttpResponse]]
