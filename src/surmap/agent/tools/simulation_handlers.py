"""The `surmap.agent.v1.SimulationTools` handlers over a `ScenarioStore` and asset sources.

One async function per rpc; the store's SQLite and the sources' HTTP block, so each runs in a
worker thread. `simulation_tool_handlers(store, sources)` binds them by rpc name in
connect-python's `(request, ctx)` shape, ready for `surmap.agent.services.simulation_tools_module`.

Search hits are remembered by ref so `download_asset` takes the ref alone. Failures are
`ConnectError`s: `NOT_FOUND` for an asset, scenario, preset or source the station does not
have; `INVALID_ARGUMENT` for an edit the renderer would refuse; `FAILED_PRECONDITION` for a
refused licence or a source that cannot serve (e.g. no Sketchfab token).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from functools import partial
from typing import Any, TypeVar

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import simulation_contents_pb2 as contents_pb
from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.agent.services import Handler
from surmap.agent.tools.simulation_building_tools import (
    add_building_fire_tool,
    list_building_presets,
    remove_building_fire_tool,
    remove_district_tool,
    set_district_tool,
    style_building_tool,
)
from surmap.agent.tools.simulation_core import (
    SimulationTooling as SimulationTooling,
)
from surmap.agent.tools.simulation_core import (
    blocking,
    edit_scenario,
    scenario_info,
    scenario_url,
)
from surmap.simulation.asset_sources import AssetHit, AssetKind, AssetSource
from surmap.simulation.licences import check_licence
from surmap.simulation.map_floor import FloorImage, GeoBBox, OsmTileSource, TileSource, stitch_floor
from surmap.simulation.scenario_contents import scene_items, weather_line
from surmap.simulation.map_floor import (
    FloorImage,
    GeoBBox,
    OsmTileSource,
    TileSource,
    bbox_geometry,
    enu_to_wgs84,
    stitch_floor,
    wgs84_to_enu,
)
from surmap.simulation.scenario_manifest import (
    add_element,
    add_fire,
    add_model,
    behaviour_of,
    clear_map_floor,
    remove_element,
    remove_fire,
    set_behaviour,
    set_map_floor,
    set_weather,
    update_behaviour_node,
)
from surmap.simulation.scenario_store import (
    Scenario,
    ScenarioStore,
    StoredAsset,
)

DEFAULT_LIMIT = 5
T = TypeVar("T")

_KINDS: Mapping[pb.AssetKind, AssetKind] = {
    pb.ASSET_KIND_MODEL: "model",
    pb.ASSET_KIND_TEXTURE: "texture",
    pb.ASSET_KIND_HDRI: "hdri",
}
_KIND_ENUMS: Mapping[AssetKind, pb.AssetKind] = {kind: value for value, kind in _KINDS.items()}
_COLLIDERS: Mapping[pb.Collider, str] = {
    pb.COLLIDER_NONE: "none",
    pb.COLLIDER_BOX: "box",
    pb.COLLIDER_TRIMESH: "trimesh",
}


def simulation_tool_handlers(
    store: ScenarioStore,
    sources: Mapping[str, AssetSource],
    tile_source: TileSource | None = None,
) -> Mapping[str, Handler]:
    """Every `SimulationTools` rpc, by rpc name, as a `(request, ctx)` handler."""
    tooling = SimulationTooling(
        store=store,
        sources=sources,
        tile_source=tile_source or OsmTileSource(cache_dir=store.library_dir / "tile-cache"),
    )

    def bind(tool: Callable[[Any, SimulationTooling], Awaitable[Any]]) -> Handler:
        async def serve(request: object, _ctx: object) -> Any:
            return await tool(request, tooling)

        return serve

    return {
        "SearchAssets": bind(search_assets),
        "DownloadAsset": bind(download_asset),
        "ListAssets": bind(list_assets),
        "CreateScenario": bind(create_scenario),
        "AddModel": bind(add_model_tool),
        "AddElement": bind(add_element_tool),
        "RemoveElement": bind(remove_element_tool),
        "SetWeather": bind(set_weather_tool),
        "AddFire": bind(add_fire_tool),
        "RemoveFire": bind(remove_fire_tool),
        "SetBehaviour": bind(set_behaviour_tool),
        "UpdateBehaviourNode": bind(update_behaviour_node_tool),
        "GetBehaviour": bind(get_behaviour),
        "ListBuildingPresets": bind(list_building_presets),
        "SetDistrict": bind(set_district_tool),
        "RemoveDistrict": bind(remove_district_tool),
        "StyleBuilding": bind(style_building_tool),
        "AddBuildingFire": bind(add_building_fire_tool),
        "RemoveBuildingFire": bind(remove_building_fire_tool),
        "SetMapFloor": bind(set_map_floor_tool),
        "ClearMapFloor": bind(clear_map_floor_tool),
        "GeoToEnu": bind(geo_to_enu_tool),
        "EnuToGeo": bind(enu_to_geo_tool),
        "GetScenario": bind(get_scenario),
        "DescribeScenario": bind(describe_scenario),
        "ListScenarios": bind(list_scenarios),
    }


def _hit_info(hit: AssetHit) -> pb.AssetHitInfo:
    verdict = check_licence(hit.licence)
    return pb.AssetHitInfo(
        ref=hit.ref,
        source=hit.source,
        kind=_KIND_ENUMS[hit.kind],
        title=hit.title,
        author=hit.author,
        licence=hit.licence,
        accepted=verdict.accepted,
        licence_reason=verdict.reason,
        page_url=hit.page_url,
        preview_url=hit.preview_url,
    )


def _asset_info(asset: StoredAsset) -> pb.StoredAssetInfo:
    return pb.StoredAssetInfo(
        ref=asset.ref,
        kind=_KIND_ENUMS[asset.kind],
        title=asset.title,
        author=asset.author,
        licence=asset.licence,
        entry_path=asset.entry,
        files=[f.path for f in asset.files],
    )


async def search_assets(
    request: pb.SearchAssetsRequest, tooling: SimulationTooling
) -> pb.SearchAssetsResponse:
    """`SearchAssets`: ask each named source (all when none), remember the hits."""
    if request.kind not in _KINDS:
        raise ConnectError(Code.INVALID_ARGUMENT, "kind must be a model, texture or HDRI")
    kind = _KINDS[request.kind]
    names = list(request.sources) or list(tooling.sources)
    unknown = [n for n in names if n not in tooling.sources]
    if unknown:
        raise ConnectError(Code.NOT_FOUND, f"no asset source {unknown[0]!r}")
    limit = request.limit if request.HasField("limit") and request.limit > 0 else DEFAULT_LIMIT
    hits: list[AssetHit] = []
    for name in names:
        source = tooling.sources[name]
        hits += await blocking(partial(source.search, request.query, kind, limit))
    for hit in hits:
        tooling.hits[hit.ref] = hit
    return pb.SearchAssetsResponse(hits=[_hit_info(h) for h in hits])


async def download_asset(
    request: pb.DownloadAssetRequest, tooling: SimulationTooling
) -> pb.AssetResponse:
    """`DownloadAsset`: fetch a remembered, licence-accepted hit into the library."""
    hit = tooling.hits.get(request.ref)
    if hit is None:
        raise ConnectError(Code.NOT_FOUND, f"{request.ref!r} was not found by search_assets")
    source = tooling.sources[hit.source]
    stored = await blocking(lambda: tooling.store.download(source, hit))
    return pb.AssetResponse(asset=_asset_info(stored))


async def list_assets(
    _request: pb.ListAssetsRequest, tooling: SimulationTooling
) -> pb.ListAssetsResponse:
    assets = await blocking(tooling.store.assets)
    return pb.ListAssetsResponse(assets=[_asset_info(a) for a in assets])


async def create_scenario(
    request: pb.CreateScenarioRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    scenario = await blocking(lambda: tooling.store.create_scenario(request.name, request.preset))
    return pb.ScenarioResponse(scenario=scenario_info(tooling.shown(scenario)))


async def add_model_tool(
    request: pb.AddModelRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`AddModel`: place a library model at an ENU pose."""
    asset = await blocking(lambda: tooling.store.asset(request.asset_ref))
    element_id = request.element_id if request.HasField("element_id") else asset.asset_id
    collider = _COLLIDERS.get(request.collider, "box")
    p = request.position
    return await edit_scenario(
        tooling,
        request.scenario_id,
        lambda s: add_model(
            s.manifest,
            asset,
            element_id=element_id,
            position_enu=(p.east, p.north, p.up),
            yaw_deg=request.yaw_deg if request.HasField("yaw_deg") else 0.0,
            scale=request.scale if request.HasField("scale") else 1.0,
            collider=collider,
            ground_truth_kind=(
                request.ground_truth_kind if request.HasField("ground_truth_kind") else None
            ),
        ),
    )


def _xyz(point: pb.EnuPoint) -> list[float]:
    return [point.east, point.north, point.up]


def _drone_nest(nest: pb.DroneNestElement) -> dict[str, object]:
    """The `drone_nest` element of a request: `yaw_deg` and `drones` only when given."""
    element: dict[str, object] = {
        "kind": "drone_nest",
        "id": nest.id,
        "position_enu": _xyz(nest.position),
    }
    if nest.HasField("yaw_deg"):
        element["yaw_deg"] = nest.yaw_deg
    if nest.HasField("drones"):
        element["drones"] = nest.drones
    return element


def _element(request: pb.AddElementRequest) -> dict[str, object]:
    """The manifest element of an `AddElement` request (spec: scene_manifest.rs)."""
    which = request.WhichOneof("element")
    if which == "box":
        box = request.box
        element: dict[str, object] = {
            "kind": "box",
            "id": box.id,
            "material": box.material,
            "size_m": _xyz(box.size),
            "position_enu": _xyz(box.position),
            "yaw_deg": box.yaw_deg,
            "collider": box.collider,
        }
        if box.HasField("ground_truth_kind"):
            element["ground_truth"] = box.ground_truth_kind
        if box.water:
            element["water"] = True
        return element
    if which == "building":
        b = request.building
        element = {
            "kind": "building",
            "id": b.id,
            "size_m": _xyz(b.size),
            "position_enu": _xyz(b.position),
            "yaw_deg": b.yaw_deg,
        }
        if b.material:
            element["material"] = b.material
        if b.windows:
            element["windows"] = {"material": "glass"}
        return element
    if which == "collapsed_building":
        c = request.collapsed_building
        return {
            "kind": "collapsed_building",
            "id": c.id,
            "material": c.material,
            "footprint_m": [c.footprint_east_m, c.footprint_north_m],
            "position_enu": _xyz(c.position),
            "yaw_deg": c.yaw_deg,
            "seed": c.seed,
        }
    if which == "person":
        person = request.person
        person_element: dict[str, object] = {
            "kind": "person",
            "id": person.id,
            "position_enu": _xyz(person.position),
            "coat": person.coat,
            "skin": person.skin or "skin",
        }
        if person.pose:
            person_element["pose"] = person.pose
        if person.HasField("height_m"):
            person_element["height_m"] = person.height_m
        if person.HasField("yaw_deg"):
            person_element["yaw_deg"] = person.yaw_deg
        return person_element
    if which == "vegetation":
        stand = request.vegetation
        return {
            "kind": "vegetation",
            "id": stand.id,
            "species": stand.species,
            "position_enu": _xyz(stand.position),
            "size_m": [stand.size_east_m, stand.size_north_m],
            "density_per_100m2": stand.density_per_100m2,
            "seed": stand.seed,
        }
    if which == "vehicle":
        vehicle = request.vehicle
        element = {
            "kind": "vehicle",
            "id": vehicle.id,
            "class": vehicle.vehicle_class,
            "position_enu": _xyz(vehicle.position),
        }
        if vehicle.HasField("yaw_deg"):
            element["yaw_deg"] = vehicle.yaw_deg
        if vehicle.cars:
            element["cars"] = vehicle.cars
        if vehicle.behaviour_json:
            element["behaviour"] = _tree_json(vehicle.behaviour_json, "vehicle behaviour")
        return element
    if which == "drone_nest":
        return _drone_nest(request.drone_nest)
    raise ConnectError(
        Code.INVALID_ARGUMENT,
        "give one of box, building, collapsed_building, person, vegetation, vehicle, drone_nest",
    )


async def add_element_tool(
    request: pb.AddElementRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    element = _element(request)
    return await edit_scenario(
        tooling, request.scenario_id, lambda s: add_element(s.manifest, element)
    )


async def remove_element_tool(
    request: pb.RemoveElementRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    return await edit_scenario(
        tooling, request.scenario_id, lambda s: remove_element(s.manifest, request.element_id)
    )


async def set_weather_tool(
    request: pb.SetWeatherRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`SetWeather`: the scenario's rain, fog visibility and one wind."""
    fog = request.fog_visibility_m if request.HasField("fog_visibility_m") else None
    return await edit_scenario(
        tooling,
        request.scenario_id,
        lambda s: set_weather(
            s.manifest,
            rain_mm_h=request.rain_mm_h,
            fog_visibility_m=fog,
            wind_from_deg=request.wind_from_deg,
            wind_speed_m_s=request.wind_speed_m_s,
            wind_gust_m_s=request.wind_gust_m_s,
        ),
    )


async def add_fire_tool(
    request: pb.AddFireRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`AddFire`: a wildfire that spreads downwind from its ignition point."""
    fire: dict[str, object] = {
        "id": request.id,
        "ignition_enu": _xyz(request.ignition),
        "start_s": request.start_s,
        "spread_m_s": request.spread_m_s,
        "max_radius_m": request.max_radius_m,
        "smoke": request.smoke if request.HasField("smoke") else True,
    }
    return await edit_scenario(tooling, request.scenario_id, lambda s: add_fire(s.manifest, fire))


async def remove_fire_tool(
    request: pb.RemoveFireRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    return await edit_scenario(
        tooling, request.scenario_id, lambda s: remove_fire(s.manifest, request.fire_id)
    )


def _tree_json(text: str, what: str) -> dict[str, object]:
    """A JSON object from a request's text; anything else is an invalid argument."""
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConnectError(Code.INVALID_ARGUMENT, f"{what} is not JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ConnectError(Code.INVALID_ARGUMENT, f"{what} must be a JSON object")
    return {str(k): v for k, v in value.items()}


async def set_behaviour_tool(
    request: pb.SetBehaviourRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`SetBehaviour`: a person's tree, or the wind's, replaced whole."""
    tree = _tree_json(request.tree_json, "the behaviour tree")
    return await edit_scenario(
        tooling,
        request.scenario_id,
        lambda s: set_behaviour(s.manifest, request.target_id, tree),
    )


async def update_behaviour_node_tool(
    request: pb.UpdateBehaviourNodeRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`UpdateBehaviourNode`: the node with that id, in a target's tree, replaced."""
    node = _tree_json(request.node_json, "the behaviour node")
    return await edit_scenario(
        tooling,
        request.scenario_id,
        lambda s: update_behaviour_node(s.manifest, request.target_id, request.node_id, node),
    )


async def get_behaviour(
    request: pb.GetBehaviourRequest, tooling: SimulationTooling
) -> pb.BehaviourResponse:
    """`GetBehaviour`: a target's tree as JSON, empty when it has none."""

    def read() -> tuple[int, dict[str, object] | None]:
        scenario = tooling.store.scenario(request.scenario_id)
        return scenario.version, behaviour_of(scenario.manifest, request.target_id)

    version, tree = await blocking(read)
    return pb.BehaviourResponse(
        target_id=request.target_id,
        tree_json="" if tree is None else json.dumps(tree),
        version=version,
    )


async def set_map_floor_tool(
    request: pb.SetMapFloorRequest, tooling: SimulationTooling
) -> pb.MapFloorResponse:
    """`SetMapFloor`: stitch the bbox's tiles, store the texture, anchor the scenario."""

    def apply() -> tuple[Scenario, FloorImage, list[str]]:
        current = tooling.store.scenario(request.scenario_id)
        bbox = GeoBBox(
            sw_lat=request.sw_lat,
            sw_lon=request.sw_lon,
            ne_lat=request.ne_lat,
            ne_lon=request.ne_lon,
        )
        floor = stitch_floor(tooling.tile_source, bbox)
        texture = tooling.store.store_floor_texture(floor.png, floor.texture_path)
        saved = tooling.store.save(
            request.scenario_id,
            set_map_floor(
                current.manifest,
                sw=(bbox.sw_lat, bbox.sw_lon),
                ne=(bbox.ne_lat, bbox.ne_lon),
                texture=texture,
                zoom=floor.zoom,
            ),
        )
        warnings: list[str] = []
        elements = [e for e in _manifest_elements(current.manifest) if e.get("id") != "ground"]
        if isinstance(current.manifest.get("map_floor"), dict) and elements:
            warnings.append(
                "scenario was already based on a different map floor: existing elements "
                "kept their ENU positions and now sit somewhere else on the map"
            )
        centre_lat, centre_lon, east_m, north_m = bbox_geometry(bbox)
        for element in elements:
            position = element.get("position_enu")
            if isinstance(position, list) and len(position) >= 2:
                if abs(float(position[0])) > east_m / 2 or abs(float(position[1])) > north_m / 2:
                    warnings.append(f"element {element.get('id')!r} lies outside the new floor")
        return saved, floor, warnings

    saved, floor, warnings = await blocking(apply)
    return pb.MapFloorResponse(
        scenario=scenario_info(saved),
        centre_lat=floor.centre_lat,
        centre_lon=floor.centre_lon,
        size_east_m=floor.size_east_m,
        size_north_m=floor.size_north_m,
        zoom=floor.zoom,
        texture=floor.texture_path,
        warnings=warnings,
    )


def _manifest_elements(manifest: Mapping[str, object]) -> list[dict[str, object]]:
    elements = manifest.get("elements")
    return [e for e in elements if isinstance(e, dict)] if isinstance(elements, list) else []


def _floor_bbox(manifest: Mapping[str, object]) -> GeoBBox:
    floor = manifest.get("map_floor")
    if not isinstance(floor, dict):
        raise ConnectError(
            Code.FAILED_PRECONDITION, "scenario has no map floor; call set_map_floor first"
        )
    sw, ne = floor.get("sw"), floor.get("ne")
    if not (isinstance(sw, list) and isinstance(ne, list)):
        raise ConnectError(Code.FAILED_PRECONDITION, "scenario's map floor is malformed")
    return GeoBBox(
        sw_lat=float(sw[0]), sw_lon=float(sw[1]), ne_lat=float(ne[0]), ne_lon=float(ne[1])
    )


async def clear_map_floor_tool(
    request: pb.ClearMapFloorRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`ClearMapFloor`: remove the floor; the preset ground box comes back."""
    return await edit_scenario(tooling, request.scenario_id, lambda s: clear_map_floor(s.manifest))


async def geo_to_enu_tool(
    request: pb.GeoToEnuRequest, tooling: SimulationTooling
) -> pb.GeoToEnuResponse:
    """`GeoToEnu`: a GPS point as ENU metres from the floor centre."""

    def convert() -> tuple[float, float, bool]:
        scenario = tooling.store.scenario(request.scenario_id)
        bbox = _floor_bbox(scenario.manifest)
        centre_lat, centre_lon, east_m, north_m = bbox_geometry(bbox)
        east, north = wgs84_to_enu(request.lat, request.lon, centre_lat, centre_lon)
        inside = abs(east) <= east_m / 2 and abs(north) <= north_m / 2
        return east, north, inside

    east, north, inside = await blocking(convert)
    return pb.GeoToEnuResponse(
        position=pb.EnuPoint(east=east, north=north, up=0.0), inside_floor=inside
    )


async def enu_to_geo_tool(
    request: pb.EnuToGeoRequest, tooling: SimulationTooling
) -> pb.EnuToGeoResponse:
    """`EnuToGeo`: ENU metres from the floor centre back to a GPS point."""

    def convert() -> tuple[float, float]:
        scenario = tooling.store.scenario(request.scenario_id)
        bbox = _floor_bbox(scenario.manifest)
        centre_lat, centre_lon, _, _ = bbox_geometry(bbox)
        return enu_to_wgs84(request.position.east, request.position.north, centre_lat, centre_lon)

    lat, lon = await blocking(convert)
    return pb.EnuToGeoResponse(lat=lat, lon=lon)


async def get_scenario(
    request: pb.GetScenarioRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    scenario = await blocking(lambda: tooling.shown(tooling.store.scenario(request.scenario_id)))
    return pb.ScenarioResponse(scenario=scenario_info(scenario))


async def describe_scenario(
    request: contents_pb.DescribeScenarioRequest, tooling: SimulationTooling
) -> contents_pb.DescribeScenarioResponse:
    """`DescribeScenario`: what the latest version holds, item by item."""
    scenario = await blocking(lambda: tooling.shown(tooling.store.scenario(request.scenario_id)))
    return contents_pb.DescribeScenarioResponse(
        id=scenario.id,
        name=scenario.name,
        version=scenario.version,
        url=scenario_url(scenario.id),
        weather=weather_line(scenario.manifest),
        items=[
            contents_pb.SceneItem(
                id=item.id,
                kind=item.kind,
                detail=item.detail,
                position_enu=list(item.position_enu or ()),
                has_behaviour=item.has_behaviour,
            )
            for item in scene_items(scenario.manifest)
        ],
        credits=[c.line() for c in scenario.credits],
    )


async def list_scenarios(
    _request: pb.ListScenariosRequest, tooling: SimulationTooling
) -> pb.ListScenariosResponse:
    scenarios = await blocking(tooling.store.scenarios)
    return pb.ListScenariosResponse(
        scenarios=[scenario_info(s, with_manifest=False) for s in scenarios]
    )
