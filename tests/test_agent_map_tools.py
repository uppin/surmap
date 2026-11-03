"""The map tools — place, move, navigate, route — over an in-memory scene store.

Handler tests with no model and no server: proto request in, proto response
out, `ConnectError` codes for a scene the caller got wrong.
"""

from __future__ import annotations

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import map_tools_pb2 as pb
from surmap.agent.tools.map_handlers import MapSceneStore, map_tool_handlers
from surmap.agent.tools.map_layers import InMemoryLayerCatalogue, LayerKind, LayerSpec


def a_store() -> MapSceneStore:
    return MapSceneStore()


async def test_add_map_object_places_a_glb_shape_and_bumps_the_revision() -> None:
    # Given an empty scene store
    store = a_store()

    # When a GLB shape is placed on the map
    placed = await map_tool_handlers(store)["AddMapObject"](
        pb.AddMapObjectRequest(
            label="debris pile",
            geometry_uri="surmap-glb://run-1/obj_7.glb",
            position=pb.GeoPoint(lon=8.5417, lat=47.3769),
        ),
        None,
    )

    # Then it comes back with a generated id, north-up at scale 1, at revision 1
    assert placed.object.id
    assert placed.object.label == "debris pile"
    assert placed.object.rotation_deg == 0
    assert placed.object.scale == 1
    assert placed.revision == 1


async def test_move_map_object_updates_only_the_fields_given() -> None:
    # Given a placed object
    store = a_store()
    handlers = map_tool_handlers(store)
    placed = await handlers["AddMapObject"](
        pb.AddMapObjectRequest(
            object_id="obj_7",
            label="car",
            geometry_uri="surmap-glb://run-1/obj_7.glb",
            position=pb.GeoPoint(lon=8.5417, lat=47.3769),
            scale=2,
        ),
        None,
    )

    # When it is moved east without naming a scale
    moved = await handlers["MoveMapObject"](
        pb.MoveMapObjectRequest(object_id="obj_7", position=pb.GeoPoint(lon=8.55, lat=47.3769)),
        None,
    )

    # Then the position changed, the scale did not, and the revision bumped
    assert moved.object.position.lon == 8.55
    assert moved.object.scale == placed.object.scale == 2
    assert moved.revision == 2


async def test_moving_an_unknown_object_is_not_found() -> None:
    # Given an empty scene
    handlers = map_tool_handlers(a_store())

    # When an object that was never placed is moved
    with pytest.raises(ConnectError) as caught:
        await handlers["MoveMapObject"](
            pb.MoveMapObjectRequest(object_id="nope", position=pb.GeoPoint(lon=8.5, lat=47.3)),
            None,
        )

    # Then the call is NOT_FOUND
    assert caught.value.code == Code.NOT_FOUND


async def test_adding_past_the_edge_of_the_world_is_invalid() -> None:
    # Given an empty scene
    handlers = map_tool_handlers(a_store())

    # When a shape is placed beyond the pole
    with pytest.raises(ConnectError) as caught:
        await handlers["AddMapObject"](
            pb.AddMapObjectRequest(
                label="x",
                geometry_uri="surmap-glb://r/o.glb",
                position=pb.GeoPoint(lon=8.5, lat=91),
            ),
            None,
        )

    # Then the call is INVALID_ARGUMENT
    assert caught.value.code == Code.INVALID_ARGUMENT


async def test_navigate_map_moves_the_camera_and_keeps_the_fields_left_out() -> None:
    # Given a fresh scene (camera over Zurich at zoom 16)
    handlers = map_tool_handlers(a_store())

    # When the camera zooms in without naming a centre
    navigated = await handlers["NavigateMap"](pb.NavigateMapRequest(zoom=18), None)

    # Then the zoom changed and the centre stayed on Zurich
    assert navigated.camera.zoom == 18
    assert navigated.camera.centre.lon == pytest.approx(8.5417)
    assert navigated.camera.centre.lat == pytest.approx(47.3769)


async def test_show_then_update_route_replaces_its_waypoints() -> None:
    # Given a shown route
    handlers = map_tool_handlers(a_store())
    shown = await handlers["ShowRoute"](
        pb.ShowRouteRequest(
            route_id="corridor",
            name="cleared corridor",
            waypoints=[pb.GeoPoint(lon=8.54, lat=47.37), pb.GeoPoint(lon=8.55, lat=47.38)],
        ),
        None,
    )

    # When its waypoints are replaced
    updated = await handlers["UpdateRoute"](
        pb.UpdateRouteRequest(
            route_id="corridor",
            waypoints=[pb.GeoPoint(lon=8.54, lat=47.37), pb.GeoPoint(lon=8.56, lat=47.39)],
        ),
        None,
    )

    # Then the route keeps its id and name, with the new last waypoint
    assert shown.route.id == updated.route.id == "corridor"
    assert updated.route.name == "cleared corridor"
    assert updated.route.waypoints[-1].lon == 8.56


async def test_a_route_with_one_waypoint_is_invalid() -> None:
    # Given an empty scene
    handlers = map_tool_handlers(a_store())

    # When a route is shown with a single point
    with pytest.raises(ConnectError) as caught:
        await handlers["ShowRoute"](
            pb.ShowRouteRequest(name="dot", waypoints=[pb.GeoPoint(lon=8.54, lat=47.37)]),
            None,
        )

    # Then the call is INVALID_ARGUMENT
    assert caught.value.code == Code.INVALID_ARGUMENT


async def test_get_map_scene_returns_objects_camera_and_routes_at_one_revision() -> None:
    # Given a scene with one object and one route
    handlers = map_tool_handlers(a_store())
    await handlers["AddMapObject"](
        pb.AddMapObjectRequest(
            object_id="obj_1",
            label="car",
            geometry_uri="surmap-glb://r/obj_1.glb",
            position=pb.GeoPoint(lon=8.5417, lat=47.3769),
        ),
        None,
    )
    await handlers["ShowRoute"](
        pb.ShowRouteRequest(
            route_id="r1",
            name="corridor",
            waypoints=[pb.GeoPoint(lon=8.54, lat=47.37), pb.GeoPoint(lon=8.55, lat=47.38)],
        ),
        None,
    )

    # When the whole scene is read
    scene = (await handlers["GetMapScene"](pb.GetMapSceneRequest(), None)).scene

    # Then it carries both, at the revision of the last change
    assert [obj.id for obj in scene.objects] == ["obj_1"]
    assert [route.id for route in scene.routes] == ["r1"]
    assert scene.revision == 2


async def test_a_fresh_scene_loads_the_osm_base_layer_by_default() -> None:
    # Given a fresh scene
    handlers = map_tool_handlers(a_store())

    # When its layers are listed
    listed = await handlers["ListMapLayers"](pb.ListMapLayersRequest(), None)

    # Then OpenStreetMap is there, marked default, and loaded; Overture roads are not
    by_id = {layer.id: layer for layer in listed.layers}
    assert by_id["osm"].is_default and by_id["osm"].loaded
    assert by_id["osm"].kind == pb.RASTER
    assert by_id["overture-buildings"].loaded
    assert not by_id["overture-transportation"].loaded


async def test_load_and_unload_map_layer_flips_what_the_scene_draws() -> None:
    # Given a fresh scene
    handlers = map_tool_handlers(a_store())

    # When the transportation layer is loaded and OSM unloaded
    loaded = await handlers["LoadMapLayer"](
        pb.LoadMapLayerRequest(layer_id="overture-transportation"), None
    )
    await handlers["UnloadMapLayer"](pb.UnloadMapLayerRequest(layer_id="osm"), None)
    scene = (await handlers["GetMapScene"](pb.GetMapSceneRequest(), None)).scene

    # Then the scene draws roads, no longer draws OSM, and the revision counted both
    assert loaded.layer.loaded
    by_id = {layer.id: layer for layer in scene.layers}
    assert by_id["overture-transportation"].loaded
    assert not by_id["osm"].loaded
    assert scene.revision == 2


async def test_loading_an_unknown_layer_is_not_found() -> None:
    # Given a fresh scene
    handlers = map_tool_handlers(a_store())

    # When a layer the catalogue does not have is loaded
    with pytest.raises(ConnectError) as caught:
        await handlers["LoadMapLayer"](pb.LoadMapLayerRequest(layer_id="satellite-ultra"), None)

    # Then the call is NOT_FOUND
    assert caught.value.code == Code.NOT_FOUND


async def test_the_store_loads_layers_from_its_catalogue_port() -> None:
    # Given a store over an in-memory catalogue with one fake default layer
    fake = LayerSpec(
        id="fake-base",
        name="Fake Base",
        kind=LayerKind.RASTER,
        source_url="https://tiles.example/{z}/{x}/{y}.png",
        is_default=True,
    )
    handlers = map_tool_handlers(MapSceneStore(InMemoryLayerCatalogue((fake,))))

    # When its layers are listed
    listed = await handlers["ListMapLayers"](pb.ListMapLayersRequest(), None)

    # Then only the fake layer is there, loaded by default: no real service was reached
    assert [(layer.id, layer.loaded) for layer in listed.layers] == [("fake-base", True)]


async def test_scenes_are_isolated_by_scene_id() -> None:
    # Given an object placed on scene "a"
    handlers = map_tool_handlers(a_store())
    await handlers["AddMapObject"](
        pb.AddMapObjectRequest(
            scene_id="a",
            object_id="obj_1",
            label="car",
            geometry_uri="surmap-glb://r/obj_1.glb",
            position=pb.GeoPoint(lon=8.5417, lat=47.3769),
        ),
        None,
    )

    # When scene "b" is listed
    listed = await handlers["ListMapObjects"](pb.ListMapObjectsRequest(scene_id="b"), None)

    # Then it is empty: scenes do not leak into each other
    assert listed.objects == []
