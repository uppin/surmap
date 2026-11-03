import { describe, expect, it } from "vitest";
import {
  DEFAULT_OVERTURE_RELEASE,
  MAP_CENTER,
  MAP_ZOOM,
  buildMapStyle,
  overtureTilesUrl,
} from "./map-style";

describe("overtureTilesUrl", () => {
  it("builds the HTTPS PMTiles URL for a theme at the pinned release", () => {
    expect(overtureTilesUrl("buildings")).toBe(
      `https://overturemaps-extras-us-west-2.s3.us-west-2.amazonaws.com/tiles/${DEFAULT_OVERTURE_RELEASE}/buildings.pmtiles`,
    );
  });

  it("honours an explicit release over the pinned default", () => {
    expect(overtureTilesUrl("transportation", "2026-01-21.0")).toBe(
      "https://overturemaps-extras-us-west-2.s3.us-west-2.amazonaws.com/tiles/2026-01-21.0/transportation.pmtiles",
    );
  });
});

describe("buildMapStyle", () => {
  it("loads the OpenStreetMap base layer by default under the buildings", () => {
    const style = buildMapStyle();
    const ids = style.layers.map((layer) => layer.id);

    expect(style.sources["osm"]).toMatchObject({
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      attribution: expect.stringContaining("OpenStreetMap"),
    });
    expect(ids.indexOf("osm")).toBeLessThan(ids.indexOf("buildings-3d"));
  });

  it("centres the map on the SITL capture's GPS fix in Zurich", () => {
    expect(MAP_CENTER).toEqual([8.5417, 47.3769]);
    expect(MAP_ZOOM).toBeGreaterThanOrEqual(14);
  });

  it("serves Overture buildings through the pmtiles protocol", () => {
    const style = buildMapStyle();

    expect(style.sources["overture-buildings"]).toMatchObject({
      type: "vector",
      url: `pmtiles://${overtureTilesUrl("buildings")}`,
      attribution: expect.stringContaining("Overture Maps Foundation"),
    });
  });

  it("extrudes buildings in 3D from their height property", () => {
    const style = buildMapStyle();
    const layer = style.layers.find((entry) => entry.id === "buildings-3d");
    if (layer?.type !== "fill-extrusion") throw new Error("buildings-3d is not a fill-extrusion layer");

    expect(layer).toMatchObject({ source: "overture-buildings", "source-layer": "building" });
    expect(layer.paint?.["fill-extrusion-height"]).toEqual(["coalesce", ["get", "height"], 5]);
  });
});
