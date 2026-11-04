"""The agent server's dataset thumbnail route, for the gallery cards."""

from __future__ import annotations

import json

from surmap.agent.server.routes import agent_http_routes
from surmap.agent.tools.port import CachedRecording, GalleryEntry
from surmap.agent.tools.workspace import FrameImage
from surmap.demo.datasets import ImageModality
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


class BuiltDatasets(Thumbnails):
    def datasets(self) -> tuple[GalleryEntry, ...]:
        return (a_built_dataset(),)


def a_built_dataset() -> GalleryEntry:
    """A prepared dataset with one cached RTAB-Map + SAM run."""
    run = CachedRecording(
        run_id="r-1",
        dataset_id="kitti-1",
        cache_key="rtabmap+sam=car",
        title="KITTI 1 · SAM: car",
        frames=12,
        created_at=1_700_000_000.0,
        preview_frame_id=3,
    )
    return GalleryEntry(
        dataset_id="kitti-1",
        title="KITTI 1",
        description="",
        provider="KITTI",
        license=None,
        credit="",
        modality=ImageModality.GREY,
        official_url="",
        default_prompt="car",
        prepared=True,
        frame_count=12,
        thumbnail_available=True,
        location_label="",
        gps_centre=None,
        gps_track=(),
        runs=(run,),
    )


async def test_the_gallery_json_lists_each_datasets_runs() -> None:
    # Given the agent routes over a dataset built once
    routes = agent_http_routes(Frames(), Glbs(), cors_origins=(), datasets=BuiltDatasets())
    server = InMemoryHost(ServerDescription(http_routes=routes), None)

    # When the gallery lists the datasets
    response = await server.http("GET", "/datasets")

    # Then the dataset carries its run, with its key and preview frame
    (dataset,) = json.loads(response.body)["datasets"]
    assert dataset["runs"] == [
        {
            "cache_key": "rtabmap+sam=car",
            "run_id": "r-1",
            "title": "KITTI 1 · SAM: car",
            "frames": 12,
            "created_at": 1_700_000_000.0,
            "preview_frame_id": 3,
        }
    ]
