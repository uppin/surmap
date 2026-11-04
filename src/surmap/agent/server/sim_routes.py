"""`/sim/` on the agent server: the Bevy simulation page, its assets, and the station's scenarios.

Everything the page fetches comes from one origin, so it needs no CORS:

- `/sim/` and `/sim/<file>` — the built page (`trunk build` output), when configured;
- `/sim/assets/scenarios/<id>.json` — a scenario's latest version, from the SQLite store;
- `/sim/assets/library/<source>/<id>/<file>` — downloaded assets, as fetched (SHA-256 recorded);
- `/sim/assets/<path>` — the PoC's own assets (shipped scene, camera profiles, pinned textures);
- `/sim/export/<id>.zip` — a scenario's bundle (`surmap.simulation.scenario_bundle`), as a download;
- `POST /sim/import[?into=<id>]` — a bundle stored as `into`'s next version, or as a new scenario
  (`import_simulation`): 200 with the scenario, 400 for a bad bundle, 404 for an unknown `into`.

A path that would leave its root answers 404.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs

from surmap.agent.tools.simulation_core import scenario_url
from surmap.agent.tools.simulation_handlers import SimulationTooling
from surmap.rpc.http import HttpRequest, HttpResponse
from surmap.simulation.asset_sources import AssetSource
from surmap.simulation.fleet.controller import FleetTiming
from surmap.simulation.fleet.perception import PerceptionRegistry
from surmap.simulation.fleet.registry import FleetRegistry
from surmap.simulation.map_floor import OsmTileSource, TileSource
from surmap.simulation.scenario_bundle import SUFFIX, BundleInvalid, export_bundle, import_bundle
from surmap.simulation.scenario_store import Scenario, ScenarioStore, UnknownRecord

SIM_PREFIX = "/sim/"
IMPORT_PATH = "/sim/import"
_TYPES: Mapping[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript",
    ".wasm": "application/wasm",
    ".json": "application/json",
    ".gltf": "model/gltf+json",
    ".glb": "model/gltf-binary",
    ".bin": "application/octet-stream",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".hdr": "image/vnd.radiance",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


@dataclass(frozen=True)
class SimulationRig:
    """What the agent server needs to offer simulation tools and serve `/sim/`."""

    store: ScenarioStore
    sources: Mapping[str, AssetSource]
    static_assets: Path
    """The PoC's `assets/` (scene, camera profiles, fetched pinned textures)."""
    page_dist: Path | None = None
    """A `trunk build` output to serve as the page; `/sim/` answers 404 without it."""
    fleet_timing: FleetTiming = field(default_factory=FleetTiming)
    """How long a fleet command waits for the linked page's answer."""
    fleet: FleetRegistry = field(init=False)
    """The scenarios' fleet controllers and the `/sim/fleet` links to them."""
    perception: PerceptionRegistry = field(default_factory=PerceptionRegistry)
    """The pages streaming to the stereo bridge (`--bevy-bridge-port`), by scenario: each
    drone's map and segmentation, for `drone_map_status`."""
    tile_source: TileSource | None = None
    """The map-floor tile source; the disk-cached OSM source when unset (tests inject a fake)."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "fleet", FleetRegistry(self.store, timing=self.fleet_timing))

    def tooling(self) -> SimulationTooling:
        return SimulationTooling(
            store=self.store,
            sources=self.sources,
            tile_source=self.tile_source
            or OsmTileSource(cache_dir=self.store.library_dir.parent / "tile-cache"),
        )


def _not_found() -> HttpResponse:
    return HttpResponse(status=404, body=b"not found", headers={"content-type": "text/plain"})


def _inside(root: Path, parts: Sequence[str]) -> Path | None:
    """`root/parts…` when it stays inside `root` and is a file."""
    if not parts or any(p in ("", ".", "..") for p in parts):
        return None
    candidate = (root / Path(*parts)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _file(path: Path | None) -> HttpResponse:
    if path is None:
        return _not_found()
    content_type = _TYPES.get(path.suffix.lower(), "application/octet-stream")
    return HttpResponse(status=200, body=path.read_bytes(), headers={"content-type": content_type})


def static_file(root: Path, parts: Sequence[str]) -> HttpResponse:
    """The file at `root/parts…` with its content type; 404 outside `root` or when absent."""
    return _file(_inside(root, parts))


def serve_simulation(rig: SimulationRig, raw_path: str) -> HttpResponse | None:
    """The `/sim/` response for `raw_path`, or None when the path is not under `/sim/`."""
    path = raw_path.split("?", 1)[0]
    if not (path == "/sim" or path.startswith(SIM_PREFIX)):
        return None
    parts = list(PurePosixPath(path[len(SIM_PREFIX) :]).parts) if path != "/sim" else []
    if parts[:2] == ["assets", "scenarios"] and len(parts) == 3 and parts[2].endswith(".json"):
        try:
            manifest = rig.store.scenario(parts[2][: -len(".json")]).manifest
        except UnknownRecord:
            return _not_found()
        return HttpResponse(
            status=200,
            body=json.dumps(manifest).encode(),
            headers={"content-type": "application/json", "cache-control": "no-store"},
        )
    if parts[:1] == ["export"] and len(parts) == 2 and parts[1].endswith(".zip"):
        return _export(rig.store, parts[1][: -len(".zip")])
    if parts[:2] == ["assets", "library"]:
        return _file(_inside(rig.store.library_dir, parts[2:]))
    if parts[:1] == ["assets"]:
        return _file(_inside(rig.static_assets, parts[1:]))
    if rig.page_dist is None:
        return _not_found()
    return _file(_inside(rig.page_dist, parts or ["index.html"]))


def import_simulation(rig: SimulationRig, request: HttpRequest) -> HttpResponse:
    """`POST /sim/import`: the bundle in the body stored as `?into=`'s next version, or as a new
    scenario; answered with the scenario as the chat pane shows it."""
    into = parse_qs(request.query).get("into", [""])[-1] or None
    try:
        scenario = import_bundle(rig.store, request.body, into=into)
    except UnknownRecord as exc:
        return _plain(404, str(exc))
    except BundleInvalid as exc:
        return _plain(400, str(exc))
    body = json.dumps({"scenario": _scenario_json(scenario)}).encode()
    return HttpResponse(status=200, body=body, headers={"content-type": "application/json"})


def _export(store: ScenarioStore, scenario_id: str) -> HttpResponse:
    try:
        bundle = export_bundle(store, scenario_id)
    except UnknownRecord:
        return _not_found()
    return HttpResponse(
        status=200,
        body=bundle,
        headers={
            "content-type": "application/zip",
            "content-disposition": f'attachment; filename="{scenario_id}{SUFFIX}"',
            "cache-control": "no-store",
        },
    )


def _scenario_json(scenario: Scenario) -> dict[str, object]:
    return {
        "id": scenario.id,
        "name": scenario.name,
        "version": scenario.version,
        "url": scenario_url(scenario.id),
        "credits": [credit.line() for credit in scenario.credits],
    }


def _plain(status: int, text: str) -> HttpResponse:
    return HttpResponse(
        status=status, body=text.encode(), headers={"content-type": "text/plain; charset=utf-8"}
    )
