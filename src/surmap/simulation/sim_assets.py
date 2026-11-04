"""Pinned runtime assets: the lock file and its fetcher."""

from __future__ import annotations

import hashlib
import io
import json
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class AssetHashMismatch(ValueError):
    """Downloaded bytes whose hash differs from the pin."""


@dataclass(frozen=True)
class AssetPin:
    path: str
    url: str
    sha256: str
    license: str
    source: str
    member: str | None = None
    # The credit an attribution licence (CC BY) asks for: title, author, licence.
    attribution: str | None = None


def _validate_relative(path: str) -> None:
    pure = PurePosixPath(path)
    if not path or pure.is_absolute() or Path(path).is_absolute() or ".." in pure.parts:
        raise ValueError(f"asset path must stay inside the assets directory: {path!r}")


def load_asset_pins(lock_path: Path) -> tuple[AssetPin, ...]:
    raw: object = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("asset lock must be a JSON object")
    assets = raw.get("assets")
    if not isinstance(assets, list):
        raise ValueError("asset lock must carry an assets list")
    pins: list[AssetPin] = []
    for item in assets:
        if not isinstance(item, dict):
            raise ValueError("asset pin must be a JSON object")
        fields: dict[str, str] = {}
        for key in ("path", "url", "sha256", "license", "source"):
            value = item.get(key)
            if not isinstance(value, str):
                raise ValueError(f"asset pin field {key!r} must be a string")
            fields[key] = value
        member = item.get("member")
        if member is not None and not isinstance(member, str):
            raise ValueError("asset pin member must be a string")
        attribution = item.get("attribution")
        if attribution is not None and not isinstance(attribution, str):
            raise ValueError("asset pin attribution must be a string")
        _validate_relative(fields["path"])
        pins.append(
            AssetPin(
                path=fields["path"],
                url=fields["url"],
                sha256=fields["sha256"],
                license=fields["license"],
                source=fields["source"],
                member=member,
                attribution=attribution,
            )
        )
    return tuple(pins)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Hosts that refuse a download unless it names the site that serves the file as its referer.
REFERERS = {"static.poly.pizza": "https://poly.pizza/"}


def _default_opener(url: str) -> bytes:
    # ambientCG refuses urllib's default user agent.
    headers = {"User-Agent": "surmap-sim/1"}
    referer = REFERERS.get(urllib.parse.urlsplit(url).hostname or "")
    if referer is not None:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:  # pinned in the lock file
        data: bytes = response.read()
        return data


def fetch_assets(
    pins: tuple[AssetPin, ...],
    dest: Path,
    opener: Callable[[str], bytes] | None = None,
) -> None:
    open_url = opener if opener is not None else _default_opener
    dest = Path(dest)
    archives: dict[str, bytes] = {}
    for pin in pins:
        _validate_relative(pin.path)
        target = dest / pin.path
        if target.is_file() and _sha256(target.read_bytes()) == pin.sha256:
            continue
        if pin.member is not None and pin.url in archives:
            downloaded = archives[pin.url]
        else:
            downloaded = open_url(pin.url)
        if pin.member is not None:
            archives[pin.url] = downloaded
            with zipfile.ZipFile(io.BytesIO(downloaded)) as archive:
                data = archive.read(pin.member)
        else:
            data = downloaded
        if _sha256(data) != pin.sha256:
            if target.exists():
                target.unlink()
            raise AssetHashMismatch(f"{pin.path}: sha256 mismatch for {pin.url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def manifest_asset_paths(scene_path: Path) -> set[str]:
    raw: object = json.loads(Path(scene_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("scene manifest must be a JSON object")
    paths: set[str] = set()
    environment = raw.get("environment")
    if isinstance(environment, dict):
        hdri = environment.get("hdri")
        if isinstance(hdri, str):
            paths.add(hdri)
    materials = raw.get("materials")
    if isinstance(materials, dict):
        for material in materials.values():
            if isinstance(material, dict):
                for key in ("base_color", "normal", "roughness", "arm"):
                    value = material.get(key)
                    if isinstance(value, str):
                        paths.add(value)
    models = raw.get("models")
    if isinstance(models, list):
        for model in models:
            if isinstance(model, dict):
                glb = model.get("glb")
                if isinstance(glb, str):
                    paths.add(glb)
    floor = raw.get("map_floor")
    if isinstance(floor, dict):
        texture = floor.get("texture")
        if isinstance(texture, str):
            paths.add(texture)
    return paths
