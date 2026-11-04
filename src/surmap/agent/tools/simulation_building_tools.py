"""The building tools of `SimulationTools`: presets, districts, styles and building fires."""

from __future__ import annotations

from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.agent.tools.simulation_core import SimulationTooling, blocking, edit_scenario
from surmap.simulation.scenario_manifest import (
    add_building_fire,
    building_presets,
    remove_building_fire,
    remove_district,
    set_district,
    style_building,
)


async def list_building_presets(
    _request: pb.ListBuildingPresetsRequest, tooling: SimulationTooling
) -> pb.BuildingPresetsResponse:
    """`ListBuildingPresets`: facade, roof and district names, shipped and added files."""
    presets = await blocking(lambda: building_presets(tooling.store.assets_dir))
    return pb.BuildingPresetsResponse(
        facades=presets.facades, roofs=presets.roofs, districts=presets.districts
    )


async def set_district_tool(
    request: pb.SetDistrictRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`SetDistrict`: a district preset over an ENU rectangle, replacing one with that id."""
    c = request.centre
    return await edit_scenario(
        tooling,
        request.scenario_id,
        lambda s: set_district(
            s.manifest,
            request.id,
            request.preset,
            position_enu=(c.east, c.north, c.up),
            size_m=(request.size_east_m, request.size_north_m),
            seed=request.seed,
        ),
    )


async def remove_district_tool(
    request: pb.RemoveDistrictRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    return await edit_scenario(
        tooling, request.scenario_id, lambda s: remove_district(s.manifest, request.district_id)
    )


def _rgb(rgb: pb.Rgb) -> tuple[float, float, float]:
    return (rgb.r, rgb.g, rgb.b)


def _glazing(request: pb.StyleBuildingRequest) -> dict[str, object] | None:
    """`glazing` names the kind; `window_ratio` alone means punched windows of that ratio."""
    if not request.HasField("glazing") and not request.HasField("window_ratio"):
        return None
    glazing: dict[str, object] = {
        "kind": request.glazing if request.HasField("glazing") else "punched"
    }
    if request.HasField("window_ratio"):
        glazing["window_ratio"] = request.window_ratio
    return glazing


async def style_building_tool(
    request: pb.StyleBuildingRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`StyleBuilding`: one building's facade, roof, shape, colours, floors and glazing."""
    return await edit_scenario(
        tooling,
        request.scenario_id,
        lambda s: style_building(
            s.manifest,
            request.building_id,
            facade=request.facade if request.HasField("facade") else None,
            roof=request.roof if request.HasField("roof") else None,
            roof_shape=request.roof_shape if request.HasField("roof_shape") else None,
            facade_colour=_rgb(request.facade_colour)
            if request.HasField("facade_colour")
            else None,
            roof_colour=_rgb(request.roof_colour) if request.HasField("roof_colour") else None,
            floors=request.floors if request.HasField("floors") else None,
            glazing=_glazing(request),
        ),
    )


async def add_building_fire_tool(
    request: pb.AddBuildingFireRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`AddBuildingFire`: a fire inside a building on one floor, from a start time."""
    return await edit_scenario(
        tooling,
        request.scenario_id,
        lambda s: add_building_fire(
            s.manifest,
            request.id,
            building=request.building_id,
            floor=request.floor,
            start_s=request.start_s,
            assets_dir=tooling.store.assets_dir,
        ),
    )


async def remove_building_fire_tool(
    request: pb.RemoveBuildingFireRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    return await edit_scenario(
        tooling, request.scenario_id, lambda s: remove_building_fire(s.manifest, request.fire_id)
    )
