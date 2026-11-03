import { describe, expect, it } from "vitest";
import type { MapSceneView } from "@/ports";
import { objectsGeoJson, routesGeoJson } from "./map-scene";

const SCENE: MapSceneView = {
  sceneId: "default",
  revision: 3,
  camera: { centre: { lon: 8.5417, lat: 47.3769, altM: null }, zoom: 16, pitchDeg: 55, bearingDeg: -20 },
  objects: [
    {
      id: "obj_1",
      label: "car",
      geometryUri: "surmap-glb://run-1/obj_1.glb",
      position: { lon: 8.5417, lat: 47.3769, altM: null },
      rotationDeg: 30,
      scale: 2,
    },
  ],
  layers: [],
  routes: [
    {
      id: "r1",
      name: "cleared corridor",
      color: "#f59e0b",
      waypoints: [
        { lon: 8.54, lat: 47.37, altM: null },
        { lon: 8.55, lat: 47.38, altM: null },
      ],
    },
  ],
};

describe("routesGeoJson", () => {
  it("turns each route into a LineString carrying its id, name and colour", () => {
    const geojson = routesGeoJson(SCENE);

    expect(geojson.features).toHaveLength(1);
    expect(geojson.features[0].geometry).toEqual({
      type: "LineString",
      coordinates: [
        [8.54, 47.37],
        [8.55, 47.38],
      ],
    });
    expect(geojson.features[0].properties).toEqual({ id: "r1", name: "cleared corridor", color: "#f59e0b" });
  });

  it("is empty when the scene has no routes", () => {
    expect(routesGeoJson({ ...SCENE, routes: [] }).features).toEqual([]);
  });
});

describe("objectsGeoJson", () => {
  it("turns each placed object into a Point carrying its label and GLB URI", () => {
    const geojson = objectsGeoJson(SCENE);

    expect(geojson.features[0].geometry).toEqual({ type: "Point", coordinates: [8.5417, 47.3769] });
    expect(geojson.features[0].properties).toMatchObject({
      id: "obj_1",
      label: "car",
      geometryUri: "surmap-glb://run-1/obj_1.glb",
    });
  });
});
