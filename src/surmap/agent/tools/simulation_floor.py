"""The map-floor simulation tools: set/clear the floor and convert GPS <-> ENU.

Split out of `simulation_handlers` (the scene-editing tools) for the repository's
file-length gate; `simulation_handlers` registers these handlers alongside its own.
"""

from __future__ import annotations

from collections.abc import Mapping

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.agent.tools.simulation_core import (
    SimulationTooling,
    blocking,
    edit_scenario,
    scenario_info,
)
from surmap.simulation.floor_edits import clear_map_floor, set_map_floor
from surmap.simulation.map_floor import (
    FloorImage,
    GeoBBox,
    bbox_geometry,
    enu_to_wgs84,
    stitch_floor,
    wgs84_to_enu,
)
from surmap.simulation.scenario_store import Scenario


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
        attribution = getattr(tooling.tile_source, "attribution", None)
        saved = tooling.store.save(
            request.scenario_id,
            set_map_floor(
                current.manifest,
                sw=(bbox.sw_lat, bbox.sw_lon),
                ne=(bbox.ne_lat, bbox.ne_lon),
                texture=texture,
                zoom=floor.zoom,
                attribution=attribution if isinstance(attribution, str) else None,
            ),
        )
        warnings: list[str] = []
        elements = [e for e in _manifest_elements(current.manifest) if e.get("id") != "ground"]
        previous = current.manifest.get("map_floor")
        same_floor = (
            isinstance(previous, dict)
            and previous.get("sw") == [bbox.sw_lat, bbox.sw_lon]
            and previous.get("ne") == [bbox.ne_lat, bbox.ne_lon]
        )
        if isinstance(previous, dict) and not same_floor and elements:
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
