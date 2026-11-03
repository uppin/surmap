"""The agent server's dataset thumbnail route, for the gallery cards."""

from __future__ import annotations

from surmap.agent.server.routes import agent_http_routes
from surmap.agent.tools.port import GalleryEntry
from surmap.agent.tools.workspace import FrameImage
from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.in_memory import InMemoryHost
from tests.agent_server_fakes import a_jpeg

THUMB = a_jpeg((64, 48))


class Frames:
    def frame(self, run_id: str, frame_id: int) -> FrameImage | None:
        return None


class Glbs:
    def uri(self, run_id: str, object_id: str) -> str:
        return f"mem://{run_id}/{object_id}"

    def read(self, uri: str) -> bytes | None:
        return None


class Thumbnails:
    def datasets(self) -> tuple[GalleryEntry, ...]:
        return ()

    def dataset_thumbnail(self, dataset_id: str) -> bytes | None:
        return THUMB if dataset_id == "kitti-1" else None


async def test_a_prepared_datasets_thumbnail_is_served_as_a_jpeg() -> None:
    # Given the agent routes with a prepared dataset
    routes = agent_http_routes(Frames(), Glbs(), cors_origins=(), datasets=Thumbnails())
    server = InMemoryHost(ServerDescription(http_routes=routes), None)

    # When the gallery asks for its thumbnail
    response = await server.http("GET", "/datasets/kitti-1/thumbnail.jpg")

    # Then it gets the JPEG
    assert response.status == 200
    assert response.body == THUMB


async def test_an_unprepared_datasets_thumbnail_is_not_found() -> None:
    # Given the agent routes
    routes = agent_http_routes(Frames(), Glbs(), cors_origins=(), datasets=Thumbnails())
    server = InMemoryHost(ServerDescription(http_routes=routes), None)

    # When the gallery asks for a dataset with no thumbnail
    response = await server.http("GET", "/datasets/nope/thumbnail.jpg")

    # Then it is a 404, so the card can show its placeholder
    assert response.status == 404
