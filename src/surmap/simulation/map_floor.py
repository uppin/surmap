"""A simulation floor from the real map: a GPS bbox stitched from map tiles.

The domain speaks contracts only (hexagonal shape, as `surmap.slam`): a
`TileSource` port fetches one slippy-map tile, `OsmTileSource` is the native
adapter for OpenStreetMap's tile service, and `InMemoryTileSource` is the
test adapter — deterministic solid tiles, no network. Stitching is pure:
the same bbox and tiles always give the same PNG, so the texture's name is
its content hash and the station caches it by construction.

ENU follows the semantic snapshot (`surmap.map.snapshot`): x east, y north,
metres from the origin, one degree of latitude is 111 320 m and longitude
scales by cos(latitude). The floor's ENU origin is the bbox centre.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

METRES_PER_DEGREE_LATITUDE = 111_320.0
MAX_FLOOR_SIZE_M = 1000.0
MAX_TILES = 64
MAX_ZOOM = 18
TILE_PX = 256
OSM_TILE_URL_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
"""The OpenStreetMap raster tile URL template (`{z}/{x}/{y}`). The station map's OSM
layer (`surmap.agent.tools.map_layers`) imports this same constant."""
MAX_TEXTURE_PX = 4096
"""The stitched floor texture is at most this wide or tall, in pixels."""
_USER_AGENT = "SurMap/1.0 (simulation map floor; https://tile.openstreetmap.org)"
TILE_URL_ENV = "SURMAP_TILE_URL_TEMPLATE"
"""Environment override for the tile URL template (`{z}/{x}/{y}`); offline mirrors set this."""
TILE_CACHE_ENV = "SURMAP_TILE_CACHE_DIR"
"""Environment override for the on-disk tile cache directory."""


class MapFloorError(ValueError):
    """A bbox or tile fetch the map floor cannot serve, and why."""


class MapFloorUnavailable(MapFloorError):
    """The tile service could not be reached or refused a tile."""


@dataclass(frozen=True)
class GeoBBox:
    """A south-west to north-east GPS bounding box (WGS84 degrees)."""

    sw_lat: float
    sw_lon: float
    ne_lat: float
    ne_lon: float

    def __post_init__(self) -> None:
        for name, lat in (("sw_lat", self.sw_lat), ("ne_lat", self.ne_lat)):
            if not -85.0 <= lat <= 85.0:
                raise MapFloorError(f"{name} {lat} is outside the map's -85..85 latitude range")
        for name, lon in (("sw_lon", self.sw_lon), ("ne_lon", self.ne_lon)):
            if not -180.0 <= lon <= 180.0:
                raise MapFloorError(f"{name} {lon} is outside -180..180 longitude")
        if not (self.sw_lat < self.ne_lat and self.sw_lon < self.ne_lon):
            raise MapFloorError(
                "the south-west corner must be south and west of the north-east corner"
            )
        _, _, east_m, north_m = bbox_geometry(self)
        if east_m > MAX_FLOOR_SIZE_M or north_m > MAX_FLOOR_SIZE_M:
            raise MapFloorError(
                f"a map floor is at most {MAX_FLOOR_SIZE_M:.0f} m a side "
                f"(this bbox is {east_m:.0f} x {north_m:.0f} m)"
            )


def bbox_geometry(bbox: GeoBBox) -> tuple[float, float, float, float]:
    """Centre (lat, lon) and size (east, north) in metres of `bbox`."""
    centre_lat = (bbox.sw_lat + bbox.ne_lat) / 2.0
    centre_lon = (bbox.sw_lon + bbox.ne_lon) / 2.0
    north_m = (bbox.ne_lat - bbox.sw_lat) * METRES_PER_DEGREE_LATITUDE
    east_m = (
        (bbox.ne_lon - bbox.sw_lon)
        * METRES_PER_DEGREE_LATITUDE
        * math.cos(math.radians(centre_lat))
    )
    return centre_lat, centre_lon, east_m, north_m


def wgs84_to_enu(
    lat: float, lon: float, centre_lat: float, centre_lon: float
) -> tuple[float, float]:
    """ENU metres (east, north) of a WGS84 point from the floor centre."""
    north = (lat - centre_lat) * METRES_PER_DEGREE_LATITUDE
    east = (lon - centre_lon) * METRES_PER_DEGREE_LATITUDE * math.cos(math.radians(centre_lat))
    return east, north


def enu_to_wgs84(
    east: float, north: float, centre_lat: float, centre_lon: float
) -> tuple[float, float]:
    """The inverse of `wgs84_to_enu`."""
    lat = centre_lat + north / METRES_PER_DEGREE_LATITUDE
    lon = centre_lon + east / (METRES_PER_DEGREE_LATITUDE * math.cos(math.radians(centre_lat)))
    return lat, lon


class TileSource(Protocol):
    """The port: one slippy-map tile as PNG bytes."""

    def fetch_tile(self, zoom: int, x: int, y: int) -> bytes:
        """The 256x256 PNG of tile (zoom, x, y)."""
        ...


class OsmTileSource:
    """The native adapter: OpenStreetMap raster tiles over HTTPS, disk-cached.

    The URL template defaults to the station map's own OSM layer
    (`OSM_TILE_URL_TEMPLATE`); `SURMAP_TILE_URL_TEMPLATE` points it at another
    tile server or an offline mirror, and `SURMAP_TILE_CACHE_DIR` moves the
    cache. A cached tile (`<cache>/<z>/<x>/<y>.png`) is never re-fetched.
    """

    def __init__(self, *, url_template: str | None = None, cache_dir: Path | None = None) -> None:
        self._url_template = url_template or os.environ.get(TILE_URL_ENV) or OSM_TILE_URL_TEMPLATE
        cache = cache_dir or os.environ.get(TILE_CACHE_ENV)
        self._cache_dir = Path(cache) if cache else None

    @property
    def attribution(self) -> str | None:
        """Who must be credited for these tiles, when the server names one."""
        if "openstreetmap.org" in self._url_template:
            return "© OpenStreetMap contributors"
        return None

    def fetch_tile(self, zoom: int, x: int, y: int) -> bytes:
        cached = None if self._cache_dir is None else self._cache_dir / f"{zoom}/{x}/{y}.png"
        if cached is not None and cached.is_file() and not _expired(cached):
            return cached.read_bytes()
        url = self._url_template.format(z=zoom, x=x, y=y)
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = bytes(response.read())
        except OSError as exc:
            raise MapFloorUnavailable(f"could not fetch map tile {url}: {exc}") from exc
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise MapFloorUnavailable(f"map tile {url} is not a PNG; refusing to cache it")
        if cached is not None:
            _write_atomically(cached, data)
        return data


CACHE_TTL_S = 7 * 24 * 3600
"""How long a cached tile is served before it is re-fetched (OSM tiles are
short-lived; a floor may be re-stitched, and stale tiles should not live forever)."""


def _expired(path: Path) -> bool:
    import time

    return time.time() - path.stat().st_mtime > CACHE_TTL_S


def _write_atomically(path: Path, data: bytes) -> None:
    """Write via a sibling temp file and rename, so a concurrent reader never
    sees a half-written tile."""
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class InMemoryTileSource:
    """The test adapter: a deterministic solid PNG per tile, no network."""

    def __init__(self) -> None:
        self.fetched: list[tuple[int, int, int]] = []

    def fetch_tile(self, zoom: int, x: int, y: int) -> bytes:
        self.fetched.append((zoom, x, y))
        colour = ((x * 37 + zoom) % 256, (y * 91) % 256, (zoom * 53) % 256)
        image = Image.new("RGB", (TILE_PX, TILE_PX), colour)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def _global_px(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web-Mercator global pixel coordinates (origin north-west)."""
    scale = float(TILE_PX * (1 << zoom))
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * scale
    return x, y


def _tile_range(bbox: GeoBBox, zoom: int) -> tuple[int, int, int, int, int, int, int, int]:
    """Tile x/y range plus the bbox's pixel crop inside the mosaic."""
    west_px, south_px = _global_px(bbox.sw_lat, bbox.sw_lon, zoom)
    east_px, north_px = _global_px(bbox.ne_lat, bbox.ne_lon, zoom)
    x0, x1 = math.floor(west_px), math.ceil(east_px)
    y0, y1 = math.floor(north_px), math.ceil(south_px)
    tx0, tx1 = x0 // TILE_PX, (x1 - 1) // TILE_PX
    ty0, ty1 = y0 // TILE_PX, (y1 - 1) // TILE_PX
    return tx0, tx1, ty0, ty1, x0, y0, x1, y1


def choose_zoom(bbox: GeoBBox, *, max_tiles: int = MAX_TILES, max_zoom: int = MAX_ZOOM) -> int:
    """The sharpest zoom whose tile mosaic fits `max_tiles`."""
    for zoom in range(max_zoom, -1, -1):
        tx0, tx1, ty0, ty1, x0, y0, x1, y1 = _tile_range(bbox, zoom)
        tiles_fit = (tx1 - tx0 + 1) * (ty1 - ty0 + 1) <= max_tiles
        pixels_fit = (x1 - x0) <= MAX_TEXTURE_PX and (y1 - y0) <= MAX_TEXTURE_PX
        if tiles_fit and pixels_fit:
            return zoom
    raise MapFloorError("no zoom fits the tile cap for this bbox")


@dataclass(frozen=True)
class FloorImage:
    """A stitched floor: PNG bytes and the geometry the manifest records."""

    png: bytes
    zoom: int
    tiles: int
    width_px: int
    height_px: int
    centre_lat: float
    centre_lon: float
    size_east_m: float
    size_north_m: float

    @property
    def texture_path(self) -> str:
        """Where the station serves this texture, named by its content."""
        digest = hashlib.sha256(self.png).hexdigest()[:16]
        return f"library/map-floor/{digest}.png"


def stitch_floor(source: TileSource, bbox: GeoBBox, *, zoom: int | None = None) -> FloorImage:
    """Stitch and crop the tiles covering `bbox` into one floor PNG."""
    chosen = choose_zoom(bbox) if zoom is None else zoom
    tx0, tx1, ty0, ty1, x0, y0, x1, y1 = _tile_range(bbox, chosen)
    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * TILE_PX, (ty1 - ty0 + 1) * TILE_PX))
    tiles = 0
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            tile = Image.open(io.BytesIO(source.fetch_tile(chosen, tx, ty))).convert("RGB")
            mosaic.paste(tile, ((tx - tx0) * TILE_PX, (ty - ty0) * TILE_PX))
            tiles += 1
    cropped = mosaic.crop(
        (x0 - tx0 * TILE_PX, y0 - ty0 * TILE_PX, x1 - tx0 * TILE_PX, y1 - ty0 * TILE_PX)
    )
    buffer = io.BytesIO()
    cropped.save(buffer, format="PNG")
    centre_lat, centre_lon, east_m, north_m = bbox_geometry(bbox)
    return FloorImage(
        png=buffer.getvalue(),
        zoom=chosen,
        tiles=tiles,
        width_px=cropped.width,
        height_px=cropped.height,
        centre_lat=centre_lat,
        centre_lon=centre_lon,
        size_east_m=east_m,
        size_north_m=north_m,
    )


__all__ = [
    "MAX_FLOOR_SIZE_M",
    "OSM_TILE_URL_TEMPLATE",
    "FloorImage",
    "GeoBBox",
    "InMemoryTileSource",
    "MapFloorError",
    "MapFloorUnavailable",
    "OsmTileSource",
    "TileSource",
    "bbox_geometry",
    "choose_zoom",
    "enu_to_wgs84",
    "stitch_floor",
    "wgs84_to_enu",
]
