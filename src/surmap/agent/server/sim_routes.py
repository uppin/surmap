"""`/sim/` on the agent server: the Bevy simulation page, its assets, and the station's scenarios.

Everything the page fetches comes from one origin, so it needs no CORS:

- `/sim/` and `/sim/<file>` — the built page (`trunk build` output), when configured;
- `/sim/assets/scenarios/<id>.json` — a scenario's latest version, from the SQLite store;
- `/sim/assets/library/<source>/<id>/<file>` — downloaded assets, as fetched (SHA-256 recorded);
- `/sim/assets/<path>` — the PoC's own assets (shipped scene, camera profiles, pinned textures).

A path that would leave its root answers 404.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from surmap.agent.tools.simulation_handlers import SimulationTooling
from surmap.rpc.http import HttpResponse
from surmap.simulation.asset_sources import AssetSource
from surmap.simulation.scenario_store import ScenarioStore, UnknownRecord

SIM_PREFIX = "/sim/"
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

    def tooling(self) -> SimulationTooling:
        return SimulationTooling(store=self.store, sources=self.sources)


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
    if parts[:2] == ["assets", "library"]:
        return _file(_inside(rig.store.library_dir, parts[2:]))
    if parts[:1] == ["assets"]:
        return _file(_inside(rig.static_assets, parts[1:]))
    if rig.page_dist is None:
        return _not_found()
    return _file(_inside(rig.page_dist, parts or ["index.html"]))
