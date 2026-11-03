"""The agent server's plain HTTP routes, and CORS for the chat UI's dev origin.

- `GET /health` — 200 `ok`.
- `GET /geometry/<run>/<object>.glb` — the object's published GLB (`model/gltf-binary`).
- `GET /frames/<run>/<frame>.jpg` — the run's frame as a JPEG; a JPEG frame is served as it was
  recorded. `?crop=x0,y0,x1,y1` (pixels of the frame) crops it and `?max_side=<px>` downscales
  it. A malformed `crop` or `max_side` is 400.
- `OPTIONS` on any path — the CORS preflight.

An unknown run, object or frame is 404. A request whose `Origin` is one of `cors_origins` gets
`Access-Control-Allow-Origin` with that origin; any other origin gets no CORS headers.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from surmap.agent.tools.workspace import FrameImage
from surmap.rpc.description import HttpRoute

__all__ = [
    "GLB_MEDIA_TYPE",
    "HEALTH_PATH",
    "FrameReader",
    "GlbReader",
    "agent_http_routes",
]

GLB_MEDIA_TYPE = "model/gltf-binary"
HEALTH_PATH = "/health"


class FrameReader(Protocol):
    """Where the frame route reads a run's frames; `SurveyWorkspace` is one."""

    def frame(self, run_id: str, frame_id: int) -> FrameImage | None: ...


class GlbReader(Protocol):
    """Where the geometry route reads published GLBs; `GeometryStore` is one."""

    def uri(self, run_id: str, object_id: str) -> str: ...

    def read(self, uri: str) -> bytes | None: ...


def agent_http_routes(
    frames: FrameReader,
    geometry: GlbReader,
    *,
    cors_origins: Sequence[str],
) -> tuple[HttpRoute[Any], ...]:
    """The health, geometry, frame and CORS-preflight routes."""
    raise NotImplementedError  # TODO(pr-8): implement
