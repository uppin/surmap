import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DroneMapView } from "@/ports";
import { DroneMapPane } from "./DroneMapPane";

const CRUISING: DroneMapView = { droneId: "nest-sw-d1", phase: "cruising", points: 812, png: "iVBOR" };

describe("DroneMapPane", () => {
  it("shows the drone's map as the server drew it, following the drone", () => {
    render(<DroneMapPane map={CRUISING} />);

    expect(screen.getByRole("img", { name: "Live map of nest-sw-d1" })).toHaveAttribute(
      "src",
      "data:image/png;base64,iVBOR",
    );
  });

  it("names the drone, what it is doing and how many points its map has", () => {
    render(<DroneMapPane map={CRUISING} />);

    expect(screen.getByRole("region", { name: "Live map" })).toHaveTextContent(/nest-sw-d1.*cruising.*812 points/);
  });
});
