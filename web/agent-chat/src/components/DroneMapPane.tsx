import type { ReactNode } from "react";
import type { DroneMapView } from "@/ports";

export interface DroneMapPaneProps {
  /** The flying drone's map, as the agent server last drew it. */
  map: DroneMapView;
}

/**
 * The map the simulation's drone is building — RTAB-Map's cloud drawn by the agent server in the
 * demo 3D pane's Follow view: from behind and above the drone, along its heading, with a yellow
 * arrow at it.
 */
export function DroneMapPane(props: DroneMapPaneProps): ReactNode {
  const { map } = props;
  return (
    <section aria-label="Live map" className="flex flex-col gap-2 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <h2 className="font-semibold">Live map</h2>
        <span className="font-medium">{map.droneId}</span>
        <span className="text-muted-foreground">
          {map.phase} · {map.points} points
        </span>
      </div>
      <img
        src={`data:image/png;base64,${map.png}`}
        alt={`Live map of ${map.droneId}`}
        className="w-full rounded-md border bg-[#0a0c0e]"
      />
    </section>
  );
}
