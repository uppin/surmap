"""Free 3D-asset sources for simulation scenarios, behind one protocol.

Poly Haven (models, textures, HDRIs; CC0), ambientCG (materials; CC0) and Sketchfab (models,
searched only among downloadable CC0 / CC BY ones) are the three sources with free search,
free download and disaster coverage (probed 2026-11-03). Every request goes through a `Fetch`
(URL + headers → bytes) so the adapters are tested over canned payloads and the store decides
where bytes land. Search is anonymous everywhere; a Sketchfab download needs a free account
token.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

AssetKind = Literal["model", "texture", "hdri"]
Fetch = Callable[[str, Mapping[str, str]], bytes]


class AssetSourceError(RuntimeError):
    """A source refused or could not serve a request."""


@dataclass(frozen=True)
class AssetHit:
    source: str
    asset_id: str
    kind: AssetKind
    title: str
    author: str
    licence: str
    page_url: str
    preview_url: str

    @property
    def ref(self) -> str:
        return f"{self.source}:{self.asset_id}"


@dataclass(frozen=True)
class AssetFile:
    """One file of an asset: `path` relative to the asset's folder; `member` names it inside
    a zip at `url` when the source ships archives."""

    path: str
    url: str
    member: str | None = None


class AssetSource(Protocol):
    name: str

    def search(self, query: str, kind: AssetKind, limit: int) -> list[AssetHit]: ...

    def files(self, asset_id: str, kind: AssetKind) -> list[AssetFile]: ...

    def fetch_file(self, url: str) -> bytes:
        """One file a `files` entry named, through the source's own fetch."""
        ...


def http_fetch(url: str, headers: Mapping[str, str]) -> bytes:
    """The real `Fetch`: a GET with a SurMap user agent."""
    request = urllib.request.Request(url, headers={"User-Agent": "surmap-sim/1", **headers})
    with urllib.request.urlopen(request, timeout=60) as response:  # sources are fixed hosts
        data: bytes = response.read()
        return data


def _json(fetch: Fetch, url: str, headers: Mapping[str, str] | None = None) -> object:
    try:
        decoded: object = json.loads(fetch(url, headers or {}))
    except (OSError, ValueError) as exc:
        raise AssetSourceError(f"{url}: {exc}") from exc
    return decoded


def _obj(value: object) -> dict[str, object]:
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


def _str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _matches(query: str, *haystacks: str) -> bool:
    words = query.lower().split()
    text = " ".join(haystacks).lower()
    return all(word in text for word in words)


class PolyHaven:
    """api.polyhaven.com — every asset CC0."""

    name = "polyhaven"
    _TYPES: Mapping[AssetKind, str] = {"model": "models", "texture": "textures", "hdri": "hdris"}

    def __init__(self, fetch: Fetch) -> None:
        self._fetch = fetch

    def fetch_file(self, url: str) -> bytes:
        return self._fetch(url, {})

    def search(self, query: str, kind: AssetKind, limit: int) -> list[AssetHit]:
        listing = _obj(
            _json(self._fetch, f"https://api.polyhaven.com/assets?t={self._TYPES[kind]}")
        )
        hits: list[AssetHit] = []
        for asset_id, raw in listing.items():
            info = _obj(raw)
            tags = _strings(info.get("tags"))
            categories = _strings(info.get("categories"))
            title = _str(info.get("name")) or asset_id
            if not _matches(query, asset_id.replace("_", " "), title, *tags, *categories):
                continue
            authors = list(_obj(info.get("authors")))
            hits.append(
                AssetHit(
                    source=self.name,
                    asset_id=asset_id,
                    kind=kind,
                    title=title,
                    author=", ".join(authors) or "Poly Haven",
                    licence="CC0-1.0",
                    page_url=f"https://polyhaven.com/a/{asset_id}",
                    preview_url=f"https://cdn.polyhaven.com/asset_img/thumbs/{asset_id}.png?width=256",
                )
            )
            if len(hits) == limit:
                break
        return hits

    def files(self, asset_id: str, kind: AssetKind) -> list[AssetFile]:
        index = _obj(_json(self._fetch, f"https://api.polyhaven.com/files/{asset_id}"))
        if kind == "model":
            gltf = _obj(_obj(_obj(index.get("gltf")).get("2k")).get("gltf"))
            entry = _str(gltf.get("url"))
            if not entry:
                raise AssetSourceError(f"polyhaven:{asset_id} has no 2K glTF")
            files = [AssetFile(path=f"{asset_id}_2k.gltf", url=entry)]
            for rel, info in sorted(_obj(gltf.get("include")).items()):
                files.append(AssetFile(path=rel, url=_str(_obj(info).get("url"))))
            return files
        if kind == "hdri":
            hdr = _str(_obj(_obj(_obj(index.get("hdri")).get("2k")).get("hdr")).get("url"))
            if not hdr:
                raise AssetSourceError(f"polyhaven:{asset_id} has no 2K HDR")
            return [AssetFile(path=f"{asset_id}_2k.hdr", url=hdr)]
        maps = (("Diffuse", "diff"), ("nor_gl", "nor_gl"), ("arm", "arm"))
        files = []
        for key, suffix in maps:
            url = _str(_obj(_obj(_obj(index.get(key)).get("2k")).get("jpg")).get("url"))
            if url:
                files.append(AssetFile(path=f"{asset_id}_{suffix}_2k.jpg", url=url))
        if not files:
            raise AssetSourceError(f"polyhaven:{asset_id} has no 2K texture maps")
        return files


class AmbientCg:
    """ambientcg.com — PBR materials, every asset CC0; maps ship as members of a 2K-JPG zip."""

    name = "ambientcg"
    _MAPS = ("Color", "NormalGL", "Roughness")

    def __init__(self, fetch: Fetch) -> None:
        self._fetch = fetch

    def fetch_file(self, url: str) -> bytes:
        return self._fetch(url, {})

    def search(self, query: str, kind: AssetKind, limit: int) -> list[AssetHit]:
        if kind != "texture":
            return []
        q = urllib.parse.quote_plus(query)
        url = f"https://ambientcg.com/api/v2/full_json?type=Material&q={q}&limit={limit}"
        found = _obj(_json(self._fetch, url)).get("foundAssets")
        hits: list[AssetHit] = []
        for raw in found if isinstance(found, list) else []:
            info = _obj(raw)
            asset_id = _str(info.get("assetId"))
            if asset_id:
                hits.append(
                    AssetHit(
                        source=self.name,
                        asset_id=asset_id,
                        kind="texture",
                        title=_str(info.get("displayName")) or asset_id,
                        author="ambientCG",
                        licence="CC0-1.0",
                        page_url=f"https://ambientcg.com/a/{asset_id}",
                        preview_url=f"https://acg-media.struffelproductions.com/file/ambientCG-Web/media/thumbnail/256-PNG/{asset_id}.png",
                    )
                )
        return hits

    def files(self, asset_id: str, kind: AssetKind) -> list[AssetFile]:
        if kind != "texture":
            raise AssetSourceError("ambientCG carries materials only")
        archive = f"https://ambientcg.com/get?file={asset_id}_2K-JPG.zip"
        return [
            AssetFile(
                path=f"{asset_id}_2K-JPG_{name}.jpg",
                url=archive,
                member=f"{asset_id}_2K-JPG_{name}.jpg",
            )
            for name in self._MAPS
        ]


class Sketchfab:
    """api.sketchfab.com/v3 — searched only among downloadable CC0 and CC BY models."""

    name = "sketchfab"
    _LICENCES = ("cc0", "by")

    def __init__(self, fetch: Fetch, token: str | None) -> None:
        self._fetch = fetch
        self._token = token

    def fetch_file(self, url: str) -> bytes:
        return self._fetch(url, {})

    def search(self, query: str, kind: AssetKind, limit: int) -> list[AssetHit]:
        if kind != "model":
            return []
        q = urllib.parse.quote_plus(query)
        hits: list[AssetHit] = []
        for licence in self._LICENCES:
            url = (
                "https://api.sketchfab.com/v3/search?type=models&downloadable=true"
                f"&license={licence}&q={q}&count={limit}"
            )
            results = _obj(_json(self._fetch, url)).get("results")
            for raw in results if isinstance(results, list) else []:
                info = _obj(raw)
                images = _obj(info.get("thumbnails")).get("images")
                preview = (
                    _str(_obj(images[0]).get("url")) if isinstance(images, list) and images else ""
                )
                hits.append(
                    AssetHit(
                        source=self.name,
                        asset_id=_str(info.get("uid")),
                        kind="model",
                        title=_str(info.get("name")),
                        author=_str(_obj(info.get("user")).get("username")),
                        licence=_str(_obj(info.get("license")).get("label")),
                        page_url=_str(info.get("viewerUrl")),
                        preview_url=preview,
                    )
                )
        return hits[: limit * len(self._LICENCES)]

    def files(self, asset_id: str, kind: AssetKind) -> list[AssetFile]:
        if not self._token:
            raise AssetSourceError(
                "Sketchfab downloads need an API token: set SKETCHFAB_API_TOKEN "
                "(free account, sketchfab.com/settings/password)"
            )
        url = f"https://api.sketchfab.com/v3/models/{asset_id}/download"
        download = _obj(_json(self._fetch, url, {"Authorization": f"Token {self._token}"}))
        glb = _str(_obj(download.get("glb")).get("url"))
        if not glb:
            raise AssetSourceError(f"sketchfab:{asset_id} offers no GLB download")
        return [AssetFile(path="model.glb", url=glb)]
