"""The map layer catalogue: a port, its Overture/OpenStreetMap adapter, and a fake.

The domain (the scene store and handlers) speaks `LayerSpec` contracts only.
`OvertureLayerCatalogue` is the native adapter: it names the real external
sources — OpenStreetMap's raster tiles (the default base layer) and the
Overture PMTiles themes at a pinned release. `InMemoryLayerCatalogue` is the
test adapter: whatever specs it is given, no network, so handler tests never
reach a tile service. Source-layer names are the ones the published PMTiles
carry (`building`, `segment`, `place`, `water`), verified against the tiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from surmap.simulation.map_floor import OSM_TILE_URL_TEMPLATE as OSM_TILE_URL_TEMPLATE

__all__ = [
    "DEFAULT_OVERTURE_RELEASE",
    "OSM_LAYER_ID",
    "OSM_TILE_URL_TEMPLATE",
    "InMemoryLayerCatalogue",
    "LayerKind",
    "LayerSpec",
    "MapLayerCatalogue",
    "OvertureLayerCatalogue",
]

DEFAULT_OVERTURE_RELEASE = "2026-10-21.0"
"""The Overture release the vector layers are pinned to; bump deliberately."""

OSM_LAYER_ID = "osm"
"""The default base layer: OpenStreetMap raster tiles."""

_OVERTURE_TILES = "https://overturemaps-extras-us-west-2.s3.us-west-2.amazonaws.com/tiles"


class LayerKind(Enum):
    """How a layer's data reaches the map."""

    RASTER = "RASTER"
    VECTOR = "VECTOR"


@dataclass(frozen=True)
class LayerSpec:
    """One catalogue layer, in domain terms (no vendor or proto types)."""

    id: str
    name: str
    kind: LayerKind
    source_url: str
    """Raster tile URL template, or the PMTiles archive URL for a vector layer."""
    source_layer: str = ""
    """Vector source layer inside the archive; empty for raster."""
    attribution: str = ""
    is_default: bool = False
    """A fresh scene loads it without being asked."""


class MapLayerCatalogue(Protocol):
    """The port: what layers exist, and each one's spec."""

    def layers(self) -> tuple[LayerSpec, ...]:
        """Every layer that can be loaded, catalogue order."""
        ...

    def layer(self, layer_id: str) -> LayerSpec | None:
        """The spec for `layer_id`, or `None` when the catalogue has no such layer."""
        ...


class OvertureLayerCatalogue:
    """The native catalogue: OpenStreetMap by default, Overture themes on request."""

    def __init__(self, release: str = DEFAULT_OVERTURE_RELEASE) -> None:
        self._layers = (
            LayerSpec(
                id=OSM_LAYER_ID,
                name="OpenStreetMap",
                kind=LayerKind.RASTER,
                source_url=OSM_TILE_URL_TEMPLATE,
                attribution="© OpenStreetMap contributors",
                is_default=True,
            ),
            LayerSpec(
                id="overture-buildings",
                name="Overture Buildings (3D)",
                kind=LayerKind.VECTOR,
                source_url=f"{_OVERTURE_TILES}/{release}/buildings.pmtiles",
                source_layer="building",
                attribution="© Overture Maps Foundation · © OpenStreetMap contributors (ODbL)",
                is_default=True,
            ),
            LayerSpec(
                id="overture-transportation",
                name="Overture Transportation",
                kind=LayerKind.VECTOR,
                source_url=f"{_OVERTURE_TILES}/{release}/transportation.pmtiles",
                source_layer="segment",
                attribution="© Overture Maps Foundation · © OpenStreetMap contributors (ODbL)",
            ),
            LayerSpec(
                id="overture-places",
                name="Overture Places",
                kind=LayerKind.VECTOR,
                source_url=f"{_OVERTURE_TILES}/{release}/places.pmtiles",
                source_layer="place",
                attribution="© Overture Maps Foundation (CDLA Permissive 2.0)",
            ),
            LayerSpec(
                id="overture-water",
                name="Overture Water",
                kind=LayerKind.VECTOR,
                source_url=f"{_OVERTURE_TILES}/{release}/base.pmtiles",
                source_layer="water",
                attribution="© Overture Maps Foundation · © OpenStreetMap contributors (ODbL)",
            ),
        )

    def layers(self) -> tuple[LayerSpec, ...]:
        return self._layers

    def layer(self, layer_id: str) -> LayerSpec | None:
        return next((spec for spec in self._layers if spec.id == layer_id), None)


class InMemoryLayerCatalogue:
    """The test adapter: a fixed catalogue in memory, no network."""

    def __init__(self, specs: tuple[LayerSpec, ...]) -> None:
        self._layers = specs

    def layers(self) -> tuple[LayerSpec, ...]:
        return self._layers

    def layer(self, layer_id: str) -> LayerSpec | None:
        return next((spec for spec in self._layers if spec.id == layer_id), None)
