import maplibregl, { type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { MAP_CENTER, MAP_ZOOM, buildMapStyle } from "@/lib/map-style";
import { objectsGeoJson, routesGeoJson } from "@/lib/map-scene";
import type { MapSceneView } from "@/ports";

/** A mounted map: `update` redraws one scene, the return of `mountMap` releases it. */
export interface MapHandle {
  update: (scene: MapSceneView) => void;
}

let protocolRegistered = false;

/**
 * Mounts the Overture basemap into `container`. Loaded lazily by `MapPane`, so
 * MapLibre stays out of the chat's first bundle. The `pmtiles://` protocol is
 * registered once, however many panes mount. Agent edits arrive as whole scenes:
 * route lines and object markers are replaced, and the camera flies only when
 * the scene's camera actually changed (so polling never fights the user's pan).
 */
export function mountMap(container: HTMLDivElement): { handle: MapHandle; remove: () => void } {
  if (!protocolRegistered) {
    maplibregl.addProtocol("pmtiles", new Protocol().tile);
    protocolRegistered = true;
  }
  const map = new maplibregl.Map({
    container,
    style: buildMapStyle(),
    center: MAP_CENTER,
    zoom: MAP_ZOOM,
    pitch: 55,
    bearing: -20,
    attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120 }), "bottom-left");

  let loaded = false;
  let pending: MapSceneView | null = null;
  let appliedCamera = "";
  map.on("style.load", () => {
    map.addSource("map-routes", { type: "geojson", data: routesGeoJson(EMPTY) });
    map.addSource("map-objects", { type: "geojson", data: objectsGeoJson(EMPTY) });
    map.addLayer({
      id: "map-routes-line",
      type: "line",
      source: "map-routes",
      paint: { "line-color": ["get", "color"], "line-width": 4, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: "map-objects-point",
      type: "circle",
      source: "map-objects",
      paint: {
        "circle-radius": 9,
        "circle-color": "#f59e0b",
        "circle-stroke-color": "#111827",
        "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: "map-objects-label",
      type: "symbol",
      source: "map-objects",
      layout: { "text-field": ["get", "label"], "text-size": 12, "text-offset": [0, 1.4] },
      paint: { "text-color": "#f8fafc", "text-halo-color": "#0b1220", "text-halo-width": 1.5 },
    });
    loaded = true;
    if (pending) apply(pending);
  });

  function applyLayers(scene: MapSceneView): void {
    for (const layer of scene.layers) {
      const visible = layer.loaded ? "visible" : "none";
      if (layer.id === "osm" || layer.id === "overture-buildings") {
        const styleLayer = layer.id === "osm" ? "osm" : "buildings-3d";
        if (map.getLayer(styleLayer)) map.setLayoutProperty(styleLayer, "visibility", visible);
        continue;
      }
      const sourceId = `layer-${layer.id}`;
      const layerId = `${sourceId}-render`;
      if (!map.getSource(sourceId)) {
        map.addSource(sourceId, {
          type: "vector",
          url: `pmtiles://${layer.sourceUrl}`,
          attribution: layer.name,
        });
      }
      if (!map.getLayer(layerId)) {
        const render = RENDER[layer.id] ?? RENDER.default;
        map.addLayer(
          {
            id: layerId,
            type: render.type,
            source: sourceId,
            "source-layer": layer.sourceLayer,
            paint: render.paint,
          } as maplibregl.LayerSpecification,
          "map-routes-line",
        );
      }
      map.setLayoutProperty(layerId, "visibility", visible);
    }
  }

  function apply(scene: MapSceneView): void {
    applyLayers(scene);
    (map.getSource("map-routes") as GeoJSONSource | undefined)?.setData(routesGeoJson(scene));
    (map.getSource("map-objects") as GeoJSONSource | undefined)?.setData(objectsGeoJson(scene));
    const camera = scene.camera;
    const key = [camera.centre.lon, camera.centre.lat, camera.zoom, camera.pitchDeg, camera.bearingDeg].join(",");
    if (key !== appliedCamera) {
      appliedCamera = key;
      map.flyTo({
        center: [camera.centre.lon, camera.centre.lat],
        zoom: camera.zoom,
        pitch: camera.pitchDeg,
        bearing: camera.bearingDeg,
      });
    }
  }

  const handle: MapHandle = {
    update(scene) {
      if (loaded) apply(scene);
      else pending = scene;
    },
  };
  return { handle, remove: () => map.remove() };
}

const RENDER: Record<string, { type: "line" | "circle" | "fill"; paint: Record<string, unknown> }> = {
  "overture-transportation": {
    type: "line",
    paint: { "line-color": "#38bdf8", "line-width": 3, "line-opacity": 0.85 },
  },
  "overture-places": {
    type: "circle",
    paint: { "circle-radius": 5, "circle-color": "#f472b6", "circle-opacity": 0.9 },
  },
  "overture-water": {
    type: "fill",
    paint: { "fill-color": "#2563eb", "fill-opacity": 0.55 },
  },
  default: { type: "line", paint: { "line-color": "#e2e8f0", "line-width": 2 } },
};

const EMPTY: MapSceneView = {
  sceneId: "default",
  revision: 0,
  camera: { centre: { lon: MAP_CENTER[0], lat: MAP_CENTER[1], altM: null }, zoom: MAP_ZOOM, pitchDeg: 55, bearingDeg: -20 },
  objects: [],
  routes: [],
  layers: [],
};
