import type { MapSceneView } from "@/ports";

/** A GeoJSON feature collection the map sources take, one feature per route or object. */
export interface MapFeatures {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry:
      | { type: "LineString"; coordinates: [number, number][] }
      | { type: "Point"; coordinates: [number, number] };
    properties: Record<string, string>;
  }[];
}

/** Each route as a LineString carrying its id, name and colour for the line layer. */
export function routesGeoJson(scene: MapSceneView): MapFeatures {
  return {
    type: "FeatureCollection",
    features: scene.routes.map((route) => ({
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: route.waypoints.map((point) => [point.lon, point.lat] as [number, number]),
      },
      properties: { id: route.id, name: route.name, color: route.color },
    })),
  };
}

/** Each placed object as a Point carrying its id, label and GLB URI for the marker layers. */
export function objectsGeoJson(scene: MapSceneView): MapFeatures {
  return {
    type: "FeatureCollection",
    features: scene.objects.map((object) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [object.position.lon, object.position.lat] },
      properties: { id: object.id, label: object.label, geometryUri: object.geometryUri },
    })),
  };
}
