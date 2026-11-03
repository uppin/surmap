"""The `surmap.agent.v1.MapTools` handlers over an in-memory `MapSceneStore`.

One async function per rpc, each taking its decoded request and the store, so
they test with no model and no server. `map_tool_handlers(store)` binds them by
rpc name in connect-python's `(request, ctx)` shape, ready for
`surmap.agent.services.map_tools_module`.

A scene is display state only: placed GLB shapes, the camera, and drawn route
paths. Failures are `ConnectError`s: `NOT_FOUND` for an object or route the
scene does not have, `INVALID_ARGUMENT` for a position off the world, a
non-positive scale, an out-of-range zoom, or a route of fewer than two points.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import map_tools_pb2 as pb
from surmap.agent.services import Handler
from surmap.agent.tools.map_layers import (
    LayerKind,
    LayerSpec,
    MapLayerCatalogue,
    OvertureLayerCatalogue,
)

__all__ = [
    "DEFAULT_SCENE_ID",
    "MapSceneStore",
    "add_map_object",
    "clear_route",
    "get_map_scene",
    "list_map_layers",
    "list_map_objects",
    "load_map_layer",
    "map_tool_handlers",
    "move_map_object",
    "navigate_map",
    "remove_map_object",
    "show_route",
    "unload_map_layer",
    "update_route",
]

_LAYER_KINDS: dict[LayerKind, pb.MapLayerKind] = {
    LayerKind.RASTER: pb.RASTER,
    LayerKind.VECTOR: pb.VECTOR,
}

DEFAULT_SCENE_ID = "default"
"""The scene a call names when it gives no `scene_id`."""

_DEFAULT_CENTRE = pb.GeoPoint(lon=8.5417, lat=47.3769)
"""Where a fresh scene's camera opens: the SITL capture's GPS fix in Zurich."""
_DEFAULT_ZOOM = 16.0
_DEFAULT_ROUTE_COLOR = "#f59e0b"


@dataclass
class _Scene:
    objects: dict[str, pb.MapObject] = field(default_factory=dict)
    routes: dict[str, pb.MapRoute] = field(default_factory=dict)
    loaded_layers: set[str] = field(default_factory=set)
    camera: pb.MapCamera = field(
        default_factory=lambda: pb.MapCamera(
            centre=pb.GeoPoint(lon=_DEFAULT_CENTRE.lon, lat=_DEFAULT_CENTRE.lat),
            zoom=_DEFAULT_ZOOM,
            pitch_deg=55,
            bearing_deg=-20,
        )
    )
    revision: int = 0
    next_id: int = 1


class MapSceneStore:
    """Every map scene by id, created on first use. In-memory, process lifetime.

    Layers come from the `MapLayerCatalogue` port (the Overture/OpenStreetMap
    adapter in production, an in-memory one in tests); a fresh scene loads the
    catalogue's default layers, OpenStreetMap among them.
    """

    def __init__(self, catalogue: MapLayerCatalogue | None = None) -> None:
        self.catalogue: MapLayerCatalogue = (
            catalogue if catalogue is not None else OvertureLayerCatalogue()
        )
        self._scenes: dict[str, _Scene] = {}

    def scene(self, scene_id: str) -> _Scene:
        """The scene named `scene_id`, fresh (Zurich camera, default layers) when new."""
        found = self._scenes.get(scene_id)
        if found is None:
            found = _Scene(
                loaded_layers={spec.id for spec in self.catalogue.layers() if spec.is_default}
            )
            self._scenes[scene_id] = found
        return found


def map_tool_handlers(store: MapSceneStore) -> Mapping[str, Handler]:
    """Every `MapTools` rpc, by rpc name, as a `(request, ctx)` handler over `store`."""

    def bind(tool: Callable[[Any, MapSceneStore], Awaitable[Any]]) -> Handler:
        async def serve(request: object, _ctx: object) -> Any:
            return await tool(request, store)

        return serve

    return {
        "AddMapObject": bind(add_map_object),
        "MoveMapObject": bind(move_map_object),
        "RemoveMapObject": bind(remove_map_object),
        "ListMapObjects": bind(list_map_objects),
        "GetMapScene": bind(get_map_scene),
        "NavigateMap": bind(navigate_map),
        "ShowRoute": bind(show_route),
        "UpdateRoute": bind(update_route),
        "ClearRoute": bind(clear_route),
        "ListMapLayers": bind(list_map_layers),
        "LoadMapLayer": bind(load_map_layer),
        "UnloadMapLayer": bind(unload_map_layer),
    }


async def add_map_object(
    request: pb.AddMapObjectRequest, store: MapSceneStore
) -> pb.MapObjectResponse:
    """`AddMapObject`: place a GLB shape at `position`; a generated id when none is given."""
    scene = store.scene(_scene_id(request))
    _require_point(request.position)
    scale = request.scale if request.HasField("scale") else 1.0
    _require_scale(scale)
    object_id = request.object_id if request.HasField("object_id") else _generated(scene, "obj")
    if object_id in scene.objects:
        raise ConnectError(Code.ALREADY_EXISTS, f"object {object_id!r} is already on the map")
    placed = pb.MapObject(
        id=object_id,
        label=request.label,
        geometry_uri=request.geometry_uri,
        position=request.position,
        rotation_deg=request.rotation_deg if request.HasField("rotation_deg") else 0.0,
        scale=scale,
    )
    scene.objects[object_id] = placed
    return pb.MapObjectResponse(object=placed, revision=_bump(scene))


async def move_map_object(
    request: pb.MoveMapObjectRequest, store: MapSceneStore
) -> pb.MapObjectResponse:
    """`MoveMapObject`: update the named fields of a placed object, keep the rest."""
    scene = store.scene(_scene_id(request))
    current = _object_or_refuse(scene, request.object_id)
    if request.HasField("position"):
        _require_point(request.position)
    if request.HasField("scale"):
        _require_scale(request.scale)
    moved = pb.MapObject()
    moved.CopyFrom(current)
    if request.HasField("position"):
        moved.position.CopyFrom(request.position)
    if request.HasField("rotation_deg"):
        moved.rotation_deg = request.rotation_deg
    if request.HasField("scale"):
        moved.scale = request.scale
    scene.objects[moved.id] = moved
    return pb.MapObjectResponse(object=moved, revision=_bump(scene))


async def remove_map_object(
    request: pb.RemoveMapObjectRequest, store: MapSceneStore
) -> pb.RemoveMapObjectResponse:
    """`RemoveMapObject`: take a placed object off the map."""
    scene = store.scene(_scene_id(request))
    _object_or_refuse(scene, request.object_id)
    del scene.objects[request.object_id]
    return pb.RemoveMapObjectResponse(object_id=request.object_id, revision=_bump(scene))


async def list_map_objects(
    request: pb.ListMapObjectsRequest, store: MapSceneStore
) -> pb.ListMapObjectsResponse:
    """`ListMapObjects`: the scene's objects in the order they were added."""
    scene = store.scene(_scene_id(request))
    return pb.ListMapObjectsResponse(objects=list(scene.objects.values()), revision=scene.revision)


async def get_map_scene(
    request: pb.GetMapSceneRequest, store: MapSceneStore
) -> pb.GetMapSceneResponse:
    """`GetMapScene`: objects, camera and routes at the scene's current revision."""
    scene_id = _scene_id(request)
    scene = store.scene(scene_id)
    return pb.GetMapSceneResponse(
        scene=pb.MapScene(
            scene_id=scene_id,
            objects=list(scene.objects.values()),
            camera=scene.camera,
            routes=list(scene.routes.values()),
            revision=scene.revision,
            layers=_layer_messages(store, scene),
        )
    )


async def navigate_map(
    request: pb.NavigateMapRequest, store: MapSceneStore
) -> pb.NavigateMapResponse:
    """`NavigateMap`: move the camera; fields left out keep their value. View only."""
    scene = store.scene(_scene_id(request))
    camera = pb.MapCamera()
    camera.CopyFrom(scene.camera)
    if request.HasField("centre"):
        _require_point(request.centre)
        camera.centre.CopyFrom(request.centre)
    if request.HasField("zoom"):
        if not 0 <= request.zoom <= 22:
            raise ConnectError(Code.INVALID_ARGUMENT, f"zoom {request.zoom} is outside 0..22")
        camera.zoom = request.zoom
    if request.HasField("pitch_deg"):
        if not 0 <= request.pitch_deg <= 85:
            raise ConnectError(Code.INVALID_ARGUMENT, f"pitch {request.pitch_deg} is outside 0..85")
        camera.pitch_deg = request.pitch_deg
    if request.HasField("bearing_deg"):
        camera.bearing_deg = request.bearing_deg
    scene.camera = camera
    return pb.NavigateMapResponse(camera=camera, revision=_bump(scene))


async def show_route(request: pb.ShowRouteRequest, store: MapSceneStore) -> pb.MapRouteResponse:
    """`ShowRoute`: draw a new route from at least two waypoints."""
    scene = store.scene(_scene_id(request))
    _require_waypoints(request.waypoints)
    route_id = request.route_id if request.HasField("route_id") else _generated(scene, "route")
    if route_id in scene.routes:
        raise ConnectError(Code.ALREADY_EXISTS, f"route {route_id!r} is already on the map")
    route = pb.MapRoute(
        id=route_id,
        name=request.name,
        waypoints=request.waypoints,
        color=request.color if request.HasField("color") else _DEFAULT_ROUTE_COLOR,
    )
    scene.routes[route_id] = route
    return pb.MapRouteResponse(route=route, revision=_bump(scene))


async def update_route(request: pb.UpdateRouteRequest, store: MapSceneStore) -> pb.MapRouteResponse:
    """`UpdateRoute`: replace a route's waypoints, name or colour; an empty waypoint
    list keeps the current path."""
    scene = store.scene(_scene_id(request))
    current = _route_or_refuse(scene, request.route_id)
    if request.waypoints:
        _require_waypoints(request.waypoints)
    route = pb.MapRoute()
    route.CopyFrom(current)
    if request.HasField("name"):
        route.name = request.name
    if request.waypoints:
        del route.waypoints[:]
        route.waypoints.extend(request.waypoints)
    if request.HasField("color"):
        route.color = request.color
    scene.routes[route.id] = route
    return pb.MapRouteResponse(route=route, revision=_bump(scene))


async def clear_route(request: pb.ClearRouteRequest, store: MapSceneStore) -> pb.ClearRouteResponse:
    """`ClearRoute`: take a drawn route off the map."""
    scene = store.scene(_scene_id(request))
    _route_or_refuse(scene, request.route_id)
    del scene.routes[request.route_id]
    return pb.ClearRouteResponse(route_id=request.route_id, revision=_bump(scene))


async def list_map_layers(
    request: pb.ListMapLayersRequest, store: MapSceneStore
) -> pb.ListMapLayersResponse:
    """`ListMapLayers`: the catalogue with this scene's loaded state."""
    scene = store.scene(_scene_id(request))
    return pb.ListMapLayersResponse(layers=_layer_messages(store, scene), revision=scene.revision)


async def load_map_layer(
    request: pb.LoadMapLayerRequest, store: MapSceneStore
) -> pb.MapLayerResponse:
    """`LoadMapLayer`: draw a catalogue layer; already loaded is left as it is."""
    scene = store.scene(_scene_id(request))
    spec = _layer_or_refuse(store, request.layer_id)
    revision = scene.revision
    if spec.id not in scene.loaded_layers:
        scene.loaded_layers.add(spec.id)
        revision = _bump(scene)
    return pb.MapLayerResponse(layer=_layer_message(spec, loaded=True), revision=revision)


async def unload_map_layer(
    request: pb.UnloadMapLayerRequest, store: MapSceneStore
) -> pb.MapLayerResponse:
    """`UnloadMapLayer`: stop drawing a layer, the default base included."""
    scene = store.scene(_scene_id(request))
    spec = _layer_or_refuse(store, request.layer_id)
    revision = scene.revision
    if spec.id in scene.loaded_layers:
        scene.loaded_layers.discard(spec.id)
        revision = _bump(scene)
    return pb.MapLayerResponse(layer=_layer_message(spec, loaded=False), revision=revision)


def _layer_or_refuse(store: MapSceneStore, layer_id: str) -> LayerSpec:
    spec = store.catalogue.layer(layer_id)
    if spec is None:
        raise ConnectError(Code.NOT_FOUND, f"no layer {layer_id!r} in the map catalogue")
    return spec


def _layer_message(spec: LayerSpec, *, loaded: bool) -> pb.MapLayer:
    return pb.MapLayer(
        id=spec.id,
        name=spec.name,
        kind=_LAYER_KINDS[spec.kind],
        source_url=spec.source_url,
        source_layer=spec.source_layer,
        loaded=loaded,
        attribution=spec.attribution,
        is_default=spec.is_default,
    )


def _layer_messages(store: MapSceneStore, scene: _Scene) -> list[pb.MapLayer]:
    return [
        _layer_message(spec, loaded=spec.id in scene.loaded_layers)
        for spec in store.catalogue.layers()
    ]


def _scene_id(request: Any) -> str:
    return str(request.scene_id) if request.HasField("scene_id") else DEFAULT_SCENE_ID


def _generated(scene: _Scene, prefix: str) -> str:
    object_id = f"{prefix}_{scene.next_id}"
    scene.next_id += 1
    return object_id


def _bump(scene: _Scene) -> int:
    scene.revision += 1
    return scene.revision


def _object_or_refuse(scene: _Scene, object_id: str) -> pb.MapObject:
    found = scene.objects.get(object_id)
    if found is None:
        raise ConnectError(Code.NOT_FOUND, f"no object {object_id!r} on the map")
    return found


def _route_or_refuse(scene: _Scene, route_id: str) -> pb.MapRoute:
    found = scene.routes.get(route_id)
    if found is None:
        raise ConnectError(Code.NOT_FOUND, f"no route {route_id!r} on the map")
    return found


def _require_point(point: pb.GeoPoint) -> None:
    if not -180 <= point.lon <= 180 or not -90 <= point.lat <= 90:
        raise ConnectError(
            Code.INVALID_ARGUMENT, f"position ({point.lon}, {point.lat}) is off the world"
        )


def _require_scale(scale: float) -> None:
    if scale <= 0:
        raise ConnectError(Code.INVALID_ARGUMENT, f"scale {scale} is not positive")


def _require_waypoints(waypoints: Any) -> None:
    if len(waypoints) < 2:
        raise ConnectError(Code.INVALID_ARGUMENT, "a route needs at least two waypoints")
    for point in waypoints:
        _require_point(point)
