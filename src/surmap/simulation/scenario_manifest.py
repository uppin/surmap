"""Scenario manifests: the Bevy simulation's `scene.json`, edited and validated on the station.

A scenario *is* a scene manifest (examples/bevy-sitl-poc/src/scene_manifest.rs): the station
stores and serves it, the page loads it at runtime. Edits here are pure — they return a new
manifest — and every result is validated by the same rules the renderer applies, so the
station never serves a scene the simulation would refuse.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from surmap.simulation.scenario_store import StoredAsset

Manifest = dict[str, object]
ELEMENT_KINDS = ("box", "collapsed_building", "building", "person")
COLLIDERS = ("none", "box", "trimesh")


class ScenarioInvalid(ValueError):
    """A manifest the renderer would refuse, and why."""


def _list(manifest: Mapping[str, object], key: str) -> list[dict[str, object]]:
    value = manifest.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ScenarioInvalid(f"{key} must be a list of objects")
    return [{str(k): v for k, v in item.items()} for item in value]


def _materials(manifest: Mapping[str, object]) -> dict[str, dict[str, object]]:
    value = manifest.get("materials", {})
    if not isinstance(value, dict):
        raise ScenarioInvalid("materials must be an object")
    return {str(k): v for k, v in value.items() if isinstance(v, dict)}


def _relative(path: object, what: str) -> str:
    if not isinstance(path, str) or not path:
        raise ScenarioInvalid(f"{what} must be a path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or "" in path.split("/"):
        raise ScenarioInvalid(f"{what} {path!r} must stay inside the assets")
    return path


def _element_materials(element: Mapping[str, object]) -> list[str]:
    keys: list[object] = []
    kind = element.get("kind")
    if kind == "person":
        keys += [element.get("coat"), element.get("skin")]
    else:
        keys.append(element.get("material"))
    for nested in ("scatter", "windows"):
        inner = element.get(nested)
        if isinstance(inner, dict):
            keys.append(inner.get("material"))
    return [key for key in keys if isinstance(key, str)]


def validate_manifest(manifest: Mapping[str, object]) -> None:
    """Raise `ScenarioInvalid` for anything `SceneManifest::from_json` would refuse."""
    if manifest.get("version") != 1:
        raise ScenarioInvalid(f"unsupported version {manifest.get('version')!r} (must be 1)")
    camera = _relative(manifest.get("camera"), "camera")
    if not camera.endswith(".camera.json"):
        raise ScenarioInvalid(f"camera {camera!r} must be a .camera.json profile")
    if not isinstance(manifest.get("environment"), dict):
        raise ScenarioInvalid("environment must be an object")
    materials = _materials(manifest)
    for key, material in materials.items():
        for field in ("base_color", "normal", "roughness", "arm"):
            if material.get(field) is not None:
                _relative(material.get(field), f"material {key}.{field}")
    seen: set[str] = set()
    scatters = 0
    for element in _list(manifest, "elements"):
        element_id = element.get("id")
        if not isinstance(element_id, str) or not element_id:
            raise ScenarioInvalid("every element needs an id")
        if element.get("kind") not in ELEMENT_KINDS:
            raise ScenarioInvalid(f"element {element_id}: unknown kind {element.get('kind')!r}")
        if element_id in seen:
            raise ScenarioInvalid(f"duplicate id {element_id!r}")
        seen.add(element_id)
        for key in _element_materials(element):
            if key not in materials:
                raise ScenarioInvalid(f"element {element_id}: unknown material {key!r}")
        scatters += isinstance(element.get("scatter"), dict)
    if scatters > 1:
        raise ScenarioInvalid("at most one element may scatter debris")
    for model in _list(manifest, "models"):
        model_id = model.get("id")
        if not isinstance(model_id, str) or not model_id:
            raise ScenarioInvalid("every model needs an id")
        if model_id in seen:
            raise ScenarioInvalid(f"duplicate id {model_id!r}")
        seen.add(model_id)
        glb = _relative(model.get("glb"), f"model {model_id}")
        if not glb.endswith((".glb", ".gltf")):
            raise ScenarioInvalid(f"model {model_id}: {glb!r} is not glTF")
        if model.get("collider") not in COLLIDERS:
            raise ScenarioInvalid(f"model {model_id}: collider must be one of {COLLIDERS}")


def element_ids(manifest: Mapping[str, object]) -> list[str]:
    ids = [str(e.get("id")) for e in _list(manifest, "elements")]
    return ids + [str(m.get("id")) for m in _list(manifest, "models")]


def _with(manifest: Mapping[str, object], key: str, items: Sequence[dict[str, object]]) -> Manifest:
    edited: Manifest = copy.deepcopy(dict(manifest))
    edited[key] = list(items)
    validate_manifest(edited)
    return edited


def add_element(manifest: Mapping[str, object], element: Mapping[str, object]) -> Manifest:
    """A new manifest with `element` appended (ids must stay unique)."""
    element_id = element.get("id")
    if element_id in element_ids(manifest):
        raise ScenarioInvalid(f"duplicate id {element_id!r}")
    return _with(manifest, "elements", [*_list(manifest, "elements"), dict(element)])


def add_model(
    manifest: Mapping[str, object],
    asset: StoredAsset,
    *,
    element_id: str,
    position_enu: tuple[float, float, float],
    yaw_deg: float = 0.0,
    scale: float = 1.0,
    collider: str = "box",
    ground_truth_kind: str | None = None,
) -> Manifest:
    """A new manifest placing a library model."""
    if element_id in element_ids(manifest):
        raise ScenarioInvalid(f"duplicate id {element_id!r}")
    if asset.kind != "model":
        raise ScenarioInvalid(f"{asset.ref} is a {asset.kind}, not a model")
    model: dict[str, object] = {
        "id": element_id,
        "glb": asset.entry,
        "position_enu": list(position_enu),
        "yaw_deg": yaw_deg,
        "scale": scale,
        "collider": collider,
        "ground_truth": ground_truth_kind is not None,
    }
    if ground_truth_kind is not None:
        model["kind"] = ground_truth_kind
    return _with(manifest, "models", [*_list(manifest, "models"), model])


def remove_element(manifest: Mapping[str, object], element_id: str) -> Manifest:
    """A new manifest without the element or model called `element_id`."""
    if element_id not in element_ids(manifest):
        raise ScenarioInvalid(f"no element or model {element_id!r}")
    elements = [e for e in _list(manifest, "elements") if e.get("id") != element_id]
    edited = _with(manifest, "elements", elements)
    return _with(
        edited, "models", [m for m in _list(edited, "models") if m.get("id") != element_id]
    )


def load_presets(assets_dir: Path) -> dict[str, Manifest]:
    """`earthquake-block` (the shipped scene) and `empty-lot` (its rig, sky and bare ground)."""
    block: Manifest = json.loads((Path(assets_dir) / "scene.json").read_text(encoding="utf-8"))
    materials = _materials(block)
    lot: Manifest = {
        "version": 1,
        "camera": block["camera"],
        "environment": copy.deepcopy(block["environment"]),
        "materials": {k: copy.deepcopy(v) for k, v in materials.items()},
        "elements": [
            {
                "kind": "box",
                "id": "ground",
                "material": "ground",
                "size_m": [200.0, 200.0, 0.2],
                "position_enu": [0.0, 0.0, -0.2],
                "collider": True,
            }
        ],
        "models": [],
    }
    presets = {"earthquake-block": block, "empty-lot": lot}
    for manifest in presets.values():
        validate_manifest(manifest)
    return presets
