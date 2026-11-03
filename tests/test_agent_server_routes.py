"""The agent server's HTTP routes in memory: health, object GLBs, frame JPEGs and CORS.

Frames and GLBs come from small in-memory readers; the PNG and crop cases go through n7's
`frame_image`, so they stay red until n7 is green.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from surmap.agent.server.routes import GLB_MEDIA_TYPE, agent_http_routes
from surmap.agent.tools.workspace import FrameImage, FrameSource
from surmap.objects3d import write_glb
from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.in_memory import InMemoryHost
from surmap.rpc.http import HttpResponse
from tests.agent_server_fakes import a_jpeg

UI_ORIGIN = "http://localhost:5173"
FRAME_JPEG = a_jpeg((640, 480))


class FramesOfOneRun:
    """`run-7`'s frames by id."""

    def __init__(self, **frames: FrameImage) -> None:
        self._frames = {int(key.removeprefix("f")): frame for key, frame in frames.items()}

    def frame(self, run_id: str, frame_id: int) -> FrameImage | None:
        return self._frames.get(frame_id) if run_id == "run-7" else None


class GlbsInMemory:
    def __init__(self, **glbs: bytes) -> None:
        self._glbs = {f"mem://run-7/{name}": glb for name, glb in glbs.items()}

    def uri(self, run_id: str, object_id: str) -> str:
        return f"mem://{run_id}/{object_id}"

    def read(self, uri: str) -> bytes | None:
        return self._glbs.get(uri)


def a_frame(data: bytes = FRAME_JPEG, media_type: str = "image/jpeg") -> FrameImage:
    return FrameImage(
        frame_id=2,
        t_ns=200,
        data=data,
        media_type=media_type,
        width=640,
        height=480,
        source=FrameSource.DISPLAY,
    )


def a_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), (10, 200, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def a_box_glb() -> bytes:
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    return write_glb(points, frame="map", up_axis="-y")


BOX_GLB = a_box_glb()


def a_server(
    frames: FramesOfOneRun | None = None, glbs: GlbsInMemory | None = None
) -> InMemoryHost[None]:
    routes = agent_http_routes(
        frames or FramesOfOneRun(f2=a_frame()),
        glbs or GlbsInMemory(obj_3=BOX_GLB),
        cors_origins=(UI_ORIGIN,),
    )
    return InMemoryHost(ServerDescription(http_routes=routes), None)


def header(response: HttpResponse, name: str) -> str | None:
    return {key.lower(): value for key, value in response.headers.items()}.get(name.lower())


def image_size_and_format(data: bytes) -> tuple[tuple[int, int], str | None]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size, image.format


async def test_health_answers_ok() -> None:
    # Given the agent's routes
    server = a_server()

    # When a probe asks for /health
    response = await server.http("GET", "/health")

    # Then it is up
    assert response.status == 200


async def test_an_object_s_glb_is_served_as_gltf_binary() -> None:
    # Given obj_3 of run-7 published as a GLB
    server = a_server(glbs=GlbsInMemory(obj_3=BOX_GLB))

    # When the viewer fetches it
    response = await server.http("GET", "/geometry/run-7/obj_3.glb")

    # Then it gets those bytes as model/gltf-binary
    assert (response.status, header(response, "content-type"), response.body) == (
        200,
        GLB_MEDIA_TYPE,
        BOX_GLB,
    )


async def test_an_object_with_no_published_glb_is_not_found() -> None:
    # Given run-7 with only obj_3 published
    server = a_server(glbs=GlbsInMemory(obj_3=BOX_GLB))

    # When the viewer fetches obj_9
    response = await server.http("GET", "/geometry/run-7/obj_9.glb")

    # Then there is nothing there
    assert response.status == 404


async def test_a_jpeg_frame_is_served_as_it_was_recorded() -> None:
    # Given frame 2 of run-7 recorded as a JPEG
    server = a_server(FramesOfOneRun(f2=a_frame(FRAME_JPEG)))

    # When the chat UI shows it
    response = await server.http("GET", "/frames/run-7/2.jpg")

    # Then it gets the recorded bytes as image/jpeg
    assert (response.status, header(response, "content-type"), response.body) == (
        200,
        "image/jpeg",
        FRAME_JPEG,
    )


async def test_a_png_frame_is_served_as_a_jpeg() -> None:
    # Given frame 2 of run-7 read from the scene cache as a PNG
    server = a_server(FramesOfOneRun(f2=a_frame(a_png(), "image/png")))

    # When the chat UI shows it
    response = await server.http("GET", "/frames/run-7/2.jpg")

    # Then it is re-encoded as a full-size JPEG
    assert image_size_and_format(response.body) == ((640, 480), "JPEG")


async def test_a_frame_crop_returns_just_that_box() -> None:
    # Given frame 2 of run-7, 640 x 480
    server = a_server()

    # When the UI asks for a 200 x 100 box of it
    response = await server.http("GET", "/frames/run-7/2.jpg", query="crop=100,50,300,150")

    # Then the image is that box
    assert image_size_and_format(response.body) == ((200, 100), "JPEG")


async def test_a_malformed_crop_is_a_bad_request() -> None:
    # Given frame 2 of run-7
    server = a_server()

    # When the UI sends a crop with three numbers
    response = await server.http("GET", "/frames/run-7/2.jpg", query="crop=100,50,300")

    # Then the request is refused
    assert response.status == 400


async def test_a_frame_the_run_did_not_record_is_not_found() -> None:
    # Given run-7 with only frame 2
    server = a_server()

    # When the UI asks for frame 99
    response = await server.http("GET", "/frames/run-7/99.jpg")

    # Then there is nothing there
    assert response.status == 404


async def test_a_frame_id_that_is_not_a_number_is_not_found() -> None:
    # Given run-7 with frame 2
    server = a_server()

    # When the UI asks for frame "latest"
    response = await server.http("GET", "/frames/run-7/latest.jpg")

    # Then there is no such frame
    assert response.status == 404


async def test_the_chat_ui_s_origin_is_allowed() -> None:
    # Given the routes allowing the Vite dev origin
    server = a_server()

    # When the UI's page fetches a frame
    response = await server.http("GET", "/frames/run-7/2.jpg", headers={"origin": UI_ORIGIN})

    # Then the response allows that origin
    assert header(response, "access-control-allow-origin") == UI_ORIGIN


async def test_another_origin_gets_no_cors_headers() -> None:
    # Given the routes allowing only the Vite dev origin
    server = a_server()

    # When a page from another origin fetches a frame
    response = await server.http(
        "GET", "/frames/run-7/2.jpg", headers={"origin": "http://evil.example"}
    )

    # Then nothing allows it
    assert header(response, "access-control-allow-origin") is None


async def test_a_preflight_for_a_connect_call_allows_the_ui_to_post() -> None:
    # Given the routes allowing the Vite dev origin
    server = a_server()

    # When the browser preflights a StreamTurn post
    response = await server.http(
        "OPTIONS",
        "/surmap.agent.v1.ChatService/StreamTurn",
        headers={"origin": UI_ORIGIN, "access-control-request-method": "POST"},
    )

    # Then the preflight succeeds for that origin and allows POST
    assert (
        response.status,
        header(response, "access-control-allow-origin"),
        "POST" in (header(response, "access-control-allow-methods") or ""),
    ) == (204, UI_ORIGIN, True)
