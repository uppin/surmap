"""Fakes for the simulation scenario tools: canned asset-source payloads and a recording fetch.

The shapes are the sources' real responses, trimmed to what the adapters read (probed live
2026-11-03: api.polyhaven.com, ambientcg.com/api/v2, api.sketchfab.com/v3).
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

POC_ASSETS = Path(__file__).parents[1] / "examples" / "bevy-sitl-poc" / "assets"

GLTF_BYTES = b'{"asset": {"version": "2.0"}, "buffers": [{"uri": "covered_car.bin"}]}'
BIN_BYTES = b"\x00\x01\x02\x03covered-car-geometry"
GLB_BYTES = b"glTF\x02\x00\x00\x00burnt-car"
DIFF_BYTES = b"\xff\xd8\xffground-colour"


def _json(value: object) -> bytes:
    return json.dumps(value).encode()


def _zip(members: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


POLYHAVEN_MODELS = {
    "covered_car": {
        "name": "Covered Car",
        "tags": ["car", "vehicle", "tarp"],
        "categories": ["props"],
        "authors": {"Kirill Sannikov": "All"},
    },
    "old_tyre": {"name": "Old Tyre", "tags": ["wheel"], "categories": ["props"], "authors": {}},
}
POLYHAVEN_FILES = {
    "gltf": {
        "2k": {
            "gltf": {
                "url": "https://dl.polyhaven.org/file/ph-assets/Models/gltf/2k/covered_car/covered_car_2k.gltf",
                "include": {
                    "covered_car.bin": {
                        "url": "https://dl.polyhaven.org/file/ph-assets/Models/gltf/8k/covered_car/covered_car.bin"
                    }
                },
            }
        }
    }
}
SKETCHFAB_BY = {
    "results": [
        {
            "uid": "3f1c0a",
            "name": "Burnt Car",
            "user": {"username": "photoscanner"},
            "license": {"label": "CC Attribution"},
            "viewerUrl": "https://sketchfab.com/3d-models/burnt-car-3f1c0a",
            "thumbnails": {
                "images": [{"url": "https://media.sketchfab.com/burnt.jpg", "width": 256}]
            },
        }
    ]
}
SKETCHFAB_CC0: dict[str, list[object]] = {"results": []}
SKETCHFAB_DOWNLOAD = {"glb": {"url": "https://sketchfab-prod.s3/burnt-car.glb", "size": 15}}
AMBIENTCG_SEARCH = {"foundAssets": [{"assetId": "Ground054", "displayName": "Ground 054"}]}
AMBIENTCG_ZIP = _zip(
    {
        "Ground054_2K-JPG_Color.jpg": DIFF_BYTES,
        "Ground054_2K-JPG_NormalGL.jpg": b"normal",
        "Ground054_2K-JPG_Roughness.jpg": b"rough",
    }
)

PH_MODELS = "https://dl.polyhaven.org/file/ph-assets/Models/gltf"
SF_SEARCH = "https://api.sketchfab.com/v3/search?type=models&downloadable=true"

CANNED: dict[str, bytes] = {
    "https://api.polyhaven.com/assets?t=models": _json(POLYHAVEN_MODELS),
    "https://api.polyhaven.com/files/covered_car": _json(POLYHAVEN_FILES),
    f"{PH_MODELS}/2k/covered_car/covered_car_2k.gltf": GLTF_BYTES,
    f"{PH_MODELS}/8k/covered_car/covered_car.bin": BIN_BYTES,
    f"{SF_SEARCH}&license=cc0&q=burnt+car&count=5": _json(SKETCHFAB_CC0),
    f"{SF_SEARCH}&license=by&q=burnt+car&count=5": _json(SKETCHFAB_BY),
    "https://api.sketchfab.com/v3/models/3f1c0a/download": _json(SKETCHFAB_DOWNLOAD),
    "https://sketchfab-prod.s3/burnt-car.glb": GLB_BYTES,
    "https://ambientcg.com/api/v2/full_json?type=Material&q=ground&limit=5": _json(
        AMBIENTCG_SEARCH
    ),
    "https://ambientcg.com/get?file=Ground054_2K-JPG.zip": AMBIENTCG_ZIP,
}


@dataclass
class RecordingFetch:
    """A `Fetch` answering from canned payloads and remembering every request."""

    responses: dict[str, bytes] = field(default_factory=lambda: dict(CANNED))
    requests: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes:
        self.requests.append((url, dict(headers)))
        if url not in self.responses:
            raise AssertionError(f"unexpected fetch {url}")
        return self.responses[url]

    def urls(self) -> list[str]:
        return [url for url, _ in self.requests]


def element_ids(manifest: Mapping[str, object]) -> list[str]:
    """The ids of a manifest's elements, in order (typed access for assertions)."""
    elements = manifest.get("elements")
    assert isinstance(elements, list)
    ids: list[str] = []
    for element in elements:
        assert isinstance(element, dict)
        element_id = element.get("id")
        assert isinstance(element_id, str)
        ids.append(element_id)
    return ids


def _dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return {str(k): v for k, v in value.items()}


def _dicts(manifest: Mapping[str, object], key: str) -> list[dict[str, object]]:
    items = manifest.get(key, [])
    assert isinstance(items, list)
    return [_dict(item) for item in items]


def fire_ids(manifest: Mapping[str, object]) -> list[str]:
    """The ids of a manifest's fires, in order."""
    return [str(fire["id"]) for fire in _dicts(manifest, "fires")]


def vegetation_species(manifest: Mapping[str, object]) -> set[str]:
    """The species files a manifest's vegetation stands name."""
    return {
        str(e["species"]) for e in _dicts(manifest, "elements") if e.get("kind") == "vegetation"
    }


def weather_of(manifest: Mapping[str, object]) -> dict[str, object]:
    return _dict(manifest.get("weather"))


def wind_of(manifest: Mapping[str, object]) -> dict[str, object]:
    return _dict(weather_of(manifest).get("wind"))
