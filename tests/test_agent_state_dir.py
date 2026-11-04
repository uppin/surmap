"""The agent's state dir: every store a conversation leaves state in lives under it, so a
restart of `python -m surmap.agent` over the same dir brings the chat back as it was.

A restart is a new store over the same file, as a restarted process or Modal container opens it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from surmap.agent.__main__ import config_from_args
from surmap.agent.proto import map_tools_pb2 as pb
from surmap.agent.runtime.session import SqliteConversationStore
from surmap.agent.server.app import (
    AgentServerConfig,
    build_demo_workspace,
    build_simulation_rig,
    conversation_store,
    map_scene_store,
    tool_outputs,
    usage_log_path,
)
from surmap.agent.tools.map_handlers import MapSceneStore, map_tool_handlers
from surmap.agent.tools.map_layers import InMemoryLayerCatalogue

ZURICH = pb.GeoPoint(lon=8.5417, lat=47.3769)


def a_persistent_map_store(path: Path) -> MapSceneStore:
    return MapSceneStore(InMemoryLayerCatalogue(()), db_path=path)


async def a_debris_pile_placed_on(store: MapSceneStore) -> pb.MapObjectResponse:
    response: pb.MapObjectResponse = await map_tool_handlers(store)["AddMapObject"](
        pb.AddMapObjectRequest(
            label="debris pile", geometry_uri="surmap-glb://run-1/obj_7.glb", position=ZURICH
        ),
        None,
    )
    return response


async def the_scene_of(store: MapSceneStore) -> pb.MapScene:
    response: pb.GetMapSceneResponse = await map_tool_handlers(store)["GetMapScene"](
        pb.GetMapSceneRequest(), None
    )
    return response.scene


def test_the_command_line_keeps_conversations_in_the_state_dir(tmp_path: Path) -> None:
    # Given the agent started with a state dir
    config = config_from_args(["--state-dir", str(tmp_path)], environ={})

    # When its conversation store is built
    store = conversation_store(config)

    # Then the conversations are in SQLite in that dir, so a restart over it keeps them
    assert isinstance(store, SqliteConversationStore)
    assert store.path == tmp_path / "conversations.sqlite"
    store.close()


def test_without_a_state_dir_the_command_line_keeps_its_state_under_the_cache_root(
    tmp_path: Path,
) -> None:
    # Given the agent started with no flags and the demo cache moved by the environment
    environ = {"SURMAP_DEMO_CACHE_DIR": str(tmp_path)}

    # When the command line is read
    config = config_from_args([], environ=environ)

    # Then its state, conversations included, persists under that cache root
    assert config.state_dir == tmp_path
    store = conversation_store(config)
    assert store is not None and store.path == tmp_path / "conversations.sqlite"
    store.close()


def test_a_cache_dir_on_the_command_line_is_the_default_state_dir() -> None:
    # Given the agent started with only a cache dir, as on Modal
    argv = ["--cache-dir", "/cache"]

    # When the command line is read
    config = config_from_args(argv, environ={})

    # Then the state lives there too
    assert config.state_dir == Path("/cache")


def test_an_explicit_conversations_db_wins_over_the_state_dir(tmp_path: Path) -> None:
    # Given a state dir and a conversations DB named on its own
    named = tmp_path / "elsewhere" / "chat.sqlite"
    config = AgentServerConfig(state_dir=tmp_path / "state", conversations_db=named)

    # When the conversation store is built
    store = conversation_store(config)

    # Then the named DB is used
    assert store is not None and store.path == named
    store.close()


def test_tool_outputs_and_usage_are_kept_in_the_state_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a state dir apart from the dataset cache, and no `$SURMAP_USAGE_LOG`
    monkeypatch.delenv("SURMAP_USAGE_LOG", raising=False)
    config = AgentServerConfig(state_dir=tmp_path / "state", cache_dir=tmp_path / "datasets")

    # Then saved tool outputs and the usage ledger go to the state dir
    assert tool_outputs(config).directory == tmp_path / "state" / "agent-tool-outputs"
    assert usage_log_path(config) == tmp_path / "state" / "usage.jsonl"


def test_the_simulation_store_is_kept_in_the_state_dir(tmp_path: Path) -> None:
    # Given a state dir
    config = AgentServerConfig(state_dir=tmp_path)

    # When the simulation rig is built
    rig = build_simulation_rig(config)

    # Then its scenarios are stored there
    assert rig is not None
    assert rig.store.db_path == tmp_path / "simulation" / "simulation.sqlite"


def test_run_history_and_geometry_are_kept_in_the_state_dir(tmp_path: Path) -> None:
    # Given a state dir apart from the dataset cache
    state = tmp_path / "state"
    config = AgentServerConfig(state_dir=state, cache_dir=tmp_path / "datasets", sam_fake=True)

    # When the demo workspace is built and publishes an object's geometry
    workspace = build_demo_workspace(config)
    workspace.geometry.put("run-1", "obj_7", b"glTF")

    # Then the run history and the geometry are in the state dir
    assert (state / "demo-history.db").is_file()
    assert (state / "agent-geometry" / "run-1" / "obj_7.glb").is_file()


def test_the_map_scene_is_kept_in_the_state_dir(tmp_path: Path) -> None:
    # Given a state dir
    config = AgentServerConfig(state_dir=tmp_path)

    # When the map scene store is built
    store = map_scene_store(config)

    # Then it is persisted there
    assert store.db_path == tmp_path / "map-scenes.sqlite"


def test_without_a_state_dir_the_map_scene_stays_in_memory() -> None:
    # Given a config with no state dir, as tests and embedders build it
    config = AgentServerConfig()

    # Then the map scene store keeps its scenes in memory
    assert map_scene_store(config).db_path is None


async def test_a_map_scene_survives_its_store_being_reopened(tmp_path: Path) -> None:
    # Given an object placed and the camera moved on a scene stored on disk
    db_path = tmp_path / "map-scenes.sqlite"
    first = a_persistent_map_store(db_path)
    placed = await a_debris_pile_placed_on(first)
    await map_tool_handlers(first)["NavigateMap"](pb.NavigateMapRequest(zoom=12), None)
    first.close()

    # When the store is reopened, as a restarted agent reopens it
    reopened = a_persistent_map_store(db_path)

    # Then the scene comes back as it was: the object, the camera and the revision
    scene = await the_scene_of(reopened)
    assert list(scene.objects) == [placed.object]
    assert scene.camera.zoom == 12
    assert scene.revision == 2
    reopened.close()


async def test_a_reopened_map_scene_does_not_reuse_a_generated_id(tmp_path: Path) -> None:
    # Given an object with a generated id on a scene stored on disk
    db_path = tmp_path / "map-scenes.sqlite"
    first = a_persistent_map_store(db_path)
    earlier = await a_debris_pile_placed_on(first)
    first.close()

    # When another object is placed after the store is reopened
    reopened = a_persistent_map_store(db_path)
    later = await a_debris_pile_placed_on(reopened)

    # Then it gets a new id, and both are on the map
    assert later.object.id != earlier.object.id
    assert len((await the_scene_of(reopened)).objects) == 2
    reopened.close()
