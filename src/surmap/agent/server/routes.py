"""The agent server's plain HTTP routes, and CORS for the chat UI's dev origin.

- `GET /health` — 200 `ok`.
- `GET /geometry/<run>/<object>.glb` — the object's published GLB (`model/gltf-binary`).
- `GET /frames/<run>/<frame>.jpg` — the run's frame as a JPEG; a JPEG frame is served as it was
  recorded. `?crop=x0,y0,x1,y1` (pixels of the frame) crops it and `?max_side=<px>` downscales
  it. A malformed `crop` or `max_side` is 400.
- `OPTIONS` on any path — the CORS preflight.
- With `simulation`, `GET /sim/…` and `POST /sim/import` (`surmap.agent.server.sim_routes`);
  `GET /sim/map/<id>` carries CORS headers, as the chat fetches it.
- With `web_dist`, `GET /` and `GET /assets/…` — the built chat page.
- With `gate`, `POST /auth/session` trades the pass code for a session token
  (`surmap.agent.server.access`), and every `GET` but `/health` and the page, and every other
  `POST` route here, needs one (401).

An unknown run, object or frame is 404. A request whose `Origin` is one of `cors_origins` gets
`Access-Control-Allow-Origin` with that origin; any other origin gets no CORS headers.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import parse_qs

from surmap.agent.event_log import log_event
from surmap.agent.server.access import (
    SESSION_PATH,
    UNAUTHENTICATED_HINT,
    AccessGate,
    session_cookie,
    session_token,
)
from surmap.agent.server.sim_routes import (
    IMPORT_PATH,
    MAP_PREFIX,
    SimulationRig,
    drone_map,
    import_simulation,
    serve_simulation,
    static_file,
)
from surmap.agent.tools.frames import frame_image
from surmap.agent.tools.workspace import BoxXYXY, FrameImage
from surmap.demo.gallery import GalleryEntry
from surmap.rpc.description import HttpRoute
from surmap.rpc.http import HttpRequest, HttpResponse

__all__ = [
    "GLB_MEDIA_TYPE",
    "HEALTH_PATH",
    "DatasetThumbnailReader",
    "FrameReader",
    "GlbReader",
    "agent_http_routes",
]

GLB_MEDIA_TYPE = "model/gltf-binary"
HEALTH_PATH = "/health"
_ANY_PATH = "*"
"""The route key that serves every path of a method; the handler dispatches on the path."""
_CORS_METHODS = "GET, POST, OPTIONS"
_CORS_HEADERS = "content-type, connect-protocol-version, connect-timeout-ms, surmap-conversation-id"
_PREFLIGHT_MAX_AGE_S = "600"
_PLAIN = {"content-type": "text/plain; charset=utf-8"}
_JPEG = "image/jpeg"


class FrameReader(Protocol):
    """Where the frame route reads a run's frames; `SurveyWorkspace` is one."""

    def frame(self, run_id: str, frame_id: int) -> FrameImage | None: ...


class DatasetThumbnailReader(Protocol):
    """Where the dataset routes read the catalogue and thumbnails; `SurveyWorkspace` is one."""

    def datasets(self) -> Sequence[GalleryEntry]: ...

    def dataset_thumbnail(self, dataset_id: str) -> bytes | None: ...


class GlbReader(Protocol):
    """Where the geometry route reads published GLBs; `GeometryStore` is one."""

    def uri(self, run_id: str, object_id: str) -> str: ...

    def read(self, uri: str) -> bytes | None: ...


def agent_http_routes(
    frames: FrameReader,
    geometry: GlbReader,
    *,
    cors_origins: Sequence[str],
    datasets: DatasetThumbnailReader | None = None,
    simulation: SimulationRig | None = None,
    gate: AccessGate | None = None,
    web_dist: Path | None = None,
) -> tuple[HttpRoute[Any], ...]:
    """The health, geometry, frame, thumbnail, `/sim/`, page, sign-in and CORS-preflight routes."""
    origins = tuple(cors_origins)

    async def health(request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200, body=b"ok", headers={**_PLAIN, **_cors(request, origins)})

    async def serve(request: HttpRequest) -> HttpResponse:
        if web_dist is not None and (request.path == "/" or request.path.startswith("/assets/")):
            if request.path == "/":
                return static_file(web_dist, ["index.html"])
            if any(part in ("", ".", "..") for part in request.path.split("/")[1:]):
                return HttpResponse(status=404)
            return static_file(web_dist, list(PurePosixPath(request.path).parts[1:]))
        if gate is not None and not _signed_in(gate, request):
            log_event("auth_refused", surface="http", target=request.path)
            return HttpResponse(status=401, body=UNAUTHENTICATED_HINT.encode(), headers=_PLAIN)
        if simulation is not None and request.path.startswith(MAP_PREFIX):
            # Drawing the map takes a while; the event loop keeps serving meanwhile.
            mapped = await asyncio.to_thread(drone_map, simulation, request.path[len(MAP_PREFIX) :])
            return HttpResponse(
                status=mapped.status,
                body=mapped.body,
                headers={**mapped.headers, **_cors(request, origins)},
            )
        if simulation is not None:
            served = serve_simulation(simulation, request.path)
            if served is not None:
                return served
        if request.path == "/datasets" and datasets is not None:
            body = json.dumps(
                {"datasets": [_dataset_json(entry) for entry in datasets.datasets()]}
            ).encode()
            return HttpResponse(
                status=200,
                body=body,
                headers={"content-type": "application/json", **_cors(request, origins)},
            )
        response = _route(request, frames, geometry, datasets)
        return HttpResponse(
            status=response.status,
            body=response.body,
            headers={**response.headers, **_cors(request, origins)},
        )

    async def preflight(request: HttpRequest) -> HttpResponse:
        headers = {
            **_cors(request, origins),
            "access-control-allow-methods": _CORS_METHODS,
            "access-control-allow-headers": _CORS_HEADERS,
            "access-control-max-age": _PREFLIGHT_MAX_AGE_S,
        }
        return HttpResponse(status=204, headers=headers)

    async def sign_in(request: HttpRequest) -> HttpResponse:
        assert gate is not None
        try:
            code = json.loads(request.body or b"{}").get("code", "")
        except (ValueError, AttributeError):
            code = ""
        token = gate.issue(code) if isinstance(code, str) else None
        if token is None:
            log_event("auth_signin", result="refused")
            return HttpResponse(status=401, body=b"wrong access code", headers=_PLAIN)
        log_event("auth_signin", result="ok")
        body = json.dumps({"token": token, "expires_in": gate.ttl_s}).encode()
        headers = {
            "content-type": "application/json",
            "cache-control": "no-store",
            "set-cookie": session_cookie(token, gate.ttl_s),
        }
        return HttpResponse(status=200, body=body, headers=headers)

    async def import_scene(request: HttpRequest) -> HttpResponse:
        assert simulation is not None
        if gate is not None and not _signed_in(gate, request):
            log_event("auth_refused", surface="http", target=request.path)
            return HttpResponse(status=401, body=UNAUTHENTICATED_HINT.encode(), headers=_PLAIN)
        response = await asyncio.to_thread(import_simulation, simulation, request)
        return HttpResponse(
            status=response.status,
            body=response.body,
            headers={**response.headers, **_cors(request, origins)},
        )

    return (
        HttpRoute("GET", HEALTH_PATH, lambda _context: health),
        *(
            (HttpRoute("POST", IMPORT_PATH, lambda _context: import_scene),)
            if simulation is not None
            else ()
        ),
        HttpRoute("GET", _ANY_PATH, lambda _context: serve),
        HttpRoute("OPTIONS", _ANY_PATH, lambda _context: preflight),
        *((HttpRoute("POST", SESSION_PATH, lambda _context: sign_in),) if gate is not None else ()),
    )


def _signed_in(gate: AccessGate, request: HttpRequest) -> bool:
    token = session_token({key.lower(): value for key, value in request.headers.items()})
    return token is not None and gate.allows(token)


def _dataset_json(entry: GalleryEntry) -> dict[str, object]:
    """One gallery entry as the JSON the chat gallery reads."""
    licence = entry.license
    return {
        "id": entry.dataset_id,
        "title": entry.title,
        "description": entry.description,
        "provider": entry.provider,
        "license": (
            {"name": licence.name, "url": licence.url, "attribution": licence.attribution}
            if licence is not None
            else {"name": "Not specified", "url": "", "attribution": entry.credit}
        ),
        "modality": entry.modality.value,
        "official_url": entry.official_url,
        "default_prompt": entry.default_prompt,
        "prepared": entry.prepared,
        "frame_count": entry.frame_count,
        "thumbnail_available": entry.thumbnail_available,
        "thumbnail_url": entry.thumbnail_url,
        "location_label": entry.location_label,
        "gps_centre": (
            {"lon": entry.gps_centre.lon, "lat": entry.gps_centre.lat}
            if entry.gps_centre is not None
            else None
        ),
        "gps_track": [{"lon": point.lon, "lat": point.lat} for point in entry.gps_track],
        "credit": entry.credit,
        "runs": [
            {
                "cache_key": run.cache_key,
                "run_id": run.run_id,
                "title": run.title,
                "frames": run.frames,
                "created_at": run.created_at,
                "preview_frame_id": run.preview_frame_id,
            }
            for run in entry.runs
        ],
    }


def _route(
    request: HttpRequest,
    frames: FrameReader,
    geometry: GlbReader,
    datasets: DatasetThumbnailReader | None = None,
) -> HttpResponse:
    segments = request.path.split("/")
    if len(segments) != 4:
        return HttpResponse(status=404)
    _, kind, run_id, leaf = segments
    if kind == "geometry" and leaf.endswith(".glb"):
        return _glb(geometry, run_id, leaf.removesuffix(".glb"))
    if kind == "frames" and leaf.endswith(".jpg"):
        return _frame(frames, run_id, leaf.removesuffix(".jpg"), request.query)
    if kind == "datasets" and leaf == "thumbnail.jpg" and datasets is not None:
        data = datasets.dataset_thumbnail(run_id)
        if data is None:
            return HttpResponse(status=404)
        return HttpResponse(status=200, body=data, headers={"content-type": _JPEG})
    return HttpResponse(status=404)


def _glb(geometry: GlbReader, run_id: str, object_id: str) -> HttpResponse:
    try:
        data = geometry.read(geometry.uri(run_id, object_id))
    except ValueError:
        data = None
    if data is None:
        return HttpResponse(status=404)
    return HttpResponse(status=200, body=data, headers={"content-type": GLB_MEDIA_TYPE})


def _frame(frames: FrameReader, run_id: str, leaf: str, query: str) -> HttpResponse:
    try:
        frame_id = int(leaf)
    except ValueError:
        return HttpResponse(status=404)
    frame = frames.frame(run_id, frame_id)
    if frame is None:
        return HttpResponse(status=404)
    try:
        crop, max_side = _frame_options(query)
    except ValueError as error:
        return HttpResponse(status=400, body=str(error).encode())
    if crop is None and max_side is None and frame.media_type == _JPEG:
        return HttpResponse(status=200, body=frame.data, headers={"content-type": _JPEG})
    try:
        encoded = frame_image(frame.data, crop=crop, max_side=max_side)
    except ValueError as error:
        return HttpResponse(status=400, body=str(error).encode())
    return HttpResponse(status=200, body=encoded.data, headers={"content-type": encoded.media_type})


def _frame_options(query: str) -> tuple[BoxXYXY | None, int | None]:
    """The `crop` box and `max_side` a frame request asks for; `ValueError` when malformed."""
    params = parse_qs(query, keep_blank_values=True)
    crop: BoxXYXY | None = None
    if "crop" in params:
        raw = params["crop"][-1].split(",")
        if len(raw) != 4:
            raise ValueError("crop takes four numbers: x0,y0,x1,y1")
        values = tuple(float(value) for value in raw)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("crop takes four finite numbers: x0,y0,x1,y1")
        crop = (values[0], values[1], values[2], values[3])
    max_side: int | None = None
    if "max_side" in params:
        max_side = int(params["max_side"][-1])
        if max_side < 1:
            raise ValueError("max_side must be at least 1 pixel")
    return crop, max_side


def _cors(request: HttpRequest, origins: tuple[str, ...]) -> dict[str, str]:
    """The CORS headers for a request from one of `origins`; none for any other origin."""
    origin = _header(request.headers, "origin")
    if origin is None or origin not in origins:
        return {}
    return {"access-control-allow-origin": origin, "vary": "origin"}


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """The header `name`, matched case-insensitively."""
    return {key.lower(): value for key, value in headers.items()}.get(name)
