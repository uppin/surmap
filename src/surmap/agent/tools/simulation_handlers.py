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

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from functools import partial
from typing import Any, TypeVar

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.agent.services import Handler
from surmap.simulation.asset_sources import AssetHit, AssetKind, AssetSource, AssetSourceError
from surmap.simulation.licences import check_licence
from surmap.simulation.scenario_manifest import (
    ScenarioInvalid,
    add_element,
    add_model,
    remove_element,
)
from surmap.simulation.scenario_store import (
    LicenceRefused,
    Scenario,
    ScenarioStore,
    StoredAsset,
    UnknownRecord,
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


@dataclass
class SimulationTooling:
    """What the handlers share: the store, the sources and the hits seen so far."""

    store: ScenarioStore
    sources: Mapping[str, AssetSource]
    hits: dict[str, AssetHit] = field(default_factory=dict)


async def _blocking(call: Callable[[], T]) -> T:
    """Run a store/source call in a thread, mapping its failures to Connect codes."""
    try:
        return await asyncio.to_thread(call)
    except UnknownRecord as exc:
        raise ConnectError(Code.NOT_FOUND, str(exc)) from exc
    except ScenarioInvalid as exc:
        raise ConnectError(Code.INVALID_ARGUMENT, str(exc)) from exc
    except (LicenceRefused, AssetSourceError) as exc:
        raise ConnectError(Code.FAILED_PRECONDITION, str(exc)) from exc


def simulation_tool_handlers(
    store: ScenarioStore, sources: Mapping[str, AssetSource]
) -> Mapping[str, Handler]:
    """Every `SimulationTools` rpc, by rpc name, as a `(request, ctx)` handler."""
    tooling = SimulationTooling(store=store, sources=sources)

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
        "GetScenario": bind(get_scenario),
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


def scenario_url(scenario_id: str) -> str:
    """Where the station's simulation page opens a scenario."""
    return f"/sim/?scenario={scenario_id}"


def _scenario_info(scenario: Scenario, *, with_manifest: bool = True) -> pb.ScenarioInfo:
    return pb.ScenarioInfo(
        id=scenario.id,
        name=scenario.name,
        version=scenario.version,
        manifest_json=json.dumps(scenario.manifest) if with_manifest else "",
        credits=[c.line() for c in scenario.credits],
        url=scenario_url(scenario.id),
        updated_at=scenario.updated_at,
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
        hits += await _blocking(partial(source.search, request.query, kind, limit))
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
    stored = await _blocking(lambda: tooling.store.download(source, hit))
    return pb.AssetResponse(asset=_asset_info(stored))


async def list_assets(
    _request: pb.ListAssetsRequest, tooling: SimulationTooling
) -> pb.ListAssetsResponse:
    assets = await _blocking(tooling.store.assets)
    return pb.ListAssetsResponse(assets=[_asset_info(a) for a in assets])


async def create_scenario(
    request: pb.CreateScenarioRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    scenario = await _blocking(lambda: tooling.store.create_scenario(request.name, request.preset))
    return pb.ScenarioResponse(scenario=_scenario_info(scenario))


async def _edit(
    tooling: SimulationTooling, scenario_id: str, edit: Callable[[Scenario], dict[str, object]]
) -> pb.ScenarioResponse:
    def apply() -> Scenario:
        current = tooling.store.scenario(scenario_id)
        return tooling.store.save(scenario_id, edit(current))

    return pb.ScenarioResponse(scenario=_scenario_info(await _blocking(apply)))


async def add_model_tool(
    request: pb.AddModelRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    """`AddModel`: place a library model at an ENU pose."""
    asset = await _blocking(lambda: tooling.store.asset(request.asset_ref))
    element_id = request.element_id if request.HasField("element_id") else asset.asset_id
    collider = _COLLIDERS.get(request.collider, "box")
    p = request.position
    return await _edit(
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
        return element
    if which == "building":
        b = request.building
        element = {
            "kind": "building",
            "id": b.id,
            "material": b.material,
            "size_m": _xyz(b.size),
            "position_enu": _xyz(b.position),
            "yaw_deg": b.yaw_deg,
        }
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
        return {
            "kind": "person",
            "id": person.id,
            "position_enu": _xyz(person.position),
            "coat": person.coat,
            "skin": "skin",
        }
    raise ConnectError(
        Code.INVALID_ARGUMENT, "give one of box, building, collapsed_building, person"
    )


async def add_element_tool(
    request: pb.AddElementRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    element = _element(request)
    return await _edit(tooling, request.scenario_id, lambda s: add_element(s.manifest, element))


async def remove_element_tool(
    request: pb.RemoveElementRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    return await _edit(
        tooling, request.scenario_id, lambda s: remove_element(s.manifest, request.element_id)
    )


async def get_scenario(
    request: pb.GetScenarioRequest, tooling: SimulationTooling
) -> pb.ScenarioResponse:
    scenario = await _blocking(lambda: tooling.store.scenario(request.scenario_id))
    return pb.ScenarioResponse(scenario=_scenario_info(scenario))


async def list_scenarios(
    _request: pb.ListScenariosRequest, tooling: SimulationTooling
) -> pb.ListScenariosResponse:
    scenarios = await _blocking(tooling.store.scenarios)
    return pb.ListScenariosResponse(
        scenarios=[_scenario_info(s, with_manifest=False) for s in scenarios]
    )
