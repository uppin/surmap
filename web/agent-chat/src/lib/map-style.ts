import type { StyleSpecification } from "maplibre-gl";

/** The Overture release the map tiles are pinned to; bump deliberately, tiles change per release. */
export const DEFAULT_OVERTURE_RELEASE = "2026-10-21.0";

/** Where the map opens: the SITL capture's GPS fix (`tests/fixtures/sitl_capture_tiny/gps.csv`). */
export const MAP_CENTER: [number, number] = [8.5417, 47.3769];

/** Close enough for building heights to read in 3D. */
export const MAP_ZOOM = 16;

/** The HTTPS PMTiles archive for one Overture theme at one release. */
export function overtureTilesUrl(theme: string, release: string = DEFAULT_OVERTURE_RELEASE): string {
  return `https://overturemaps-extras-us-west-2.s3.us-west-2.amazonaws.com/tiles/${release}/${theme}.pmtiles`;
}

/** The default base layer's raster tiles: OpenStreetMap, loaded on every fresh map. */
export const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const OSM_ATTRIBUTION = "© OpenStreetMap contributors";

/**
 * The basemap style: the OpenStreetMap base layer (loaded by default, as the
 * agent's layer catalogue declares) plus Overture buildings extruded in 3D by
 * their `height` property. Other catalogue layers are added by the map loader
 * when the agent loads them.
 */
export function buildMapStyle(release: string = DEFAULT_OVERTURE_RELEASE): StyleSpecification {
  return {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      osm: {
        type: "raster",
        tiles: [OSM_TILE_URL],
        tileSize: 256,
        attribution: OSM_ATTRIBUTION,
      },
      "overture-buildings": {
        type: "vector",
        url: `pmtiles://${overtureTilesUrl("buildings", release)}`,
        attribution:
          "© Overture Maps Foundation · © OpenStreetMap contributors · Microsoft ML Buildings (ODbL)",
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#0b1220" } },
      { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.55 } },
      {
        id: "buildings-3d",
        type: "fill-extrusion",
        source: "overture-buildings",
        "source-layer": "building",
        minzoom: 14,
        paint: {
          "fill-extrusion-color": "#94a3b8",
          "fill-extrusion-height": ["coalesce", ["get", "height"], 5],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.85,
        },
      },
    ],
  };
}
