import { useEffect, useRef, useState, type ReactNode } from "react";
import type { MapHandle } from "@/lib/maplibre-map";
import type { MapSceneView } from "@/ports";

export interface MapPaneProps {
  /** The scene the agent last reported; `null` until the first poll answers. */
  scene: MapSceneView | null;
}

/** The embedded Overture basemap (MapLibre GL), loaded lazily so the chat bundle stays small. */
export function MapPane(props: MapPaneProps): ReactNode {
  const containerRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<MapHandle | null>(null);
  const sceneRef = useRef<MapSceneView | null>(null);
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let active = true;
    let remove: () => void = () => {};
    void import("@/lib/maplibre-map")
      .then(({ mountMap }) => {
        if (!active) return;
        const mounted = mountMap(container);
        handleRef.current = mounted.handle;
        remove = mounted.remove;
        // A scene polled before the map mounted still has to land on it.
        if (sceneRef.current) mounted.handle.update(sceneRef.current);
        setReady(true);
      })
      .catch((error: unknown) => {
        if (active) setFailure(error instanceof Error ? error.message : String(error));
      });
    return () => {
      active = false;
      handleRef.current = null;
      remove();
    };
  }, []);

  useEffect(() => {
    sceneRef.current = props.scene;
    if (props.scene) handleRef.current?.update(props.scene);
  }, [props.scene]);

  return (
    <figure aria-label="Survey map" className="flex flex-col gap-1 self-stretch">
      <div className="relative">
        <div ref={containerRef} className={`block h-80 w-full rounded-md ${ready ? "" : "invisible"}`} />
        {!ready && failure === null && (
          <p className="absolute inset-0 grid place-items-center text-xs text-muted-foreground">
            Loading map…
          </p>
        )}
      </div>
      {failure !== null && (
        <figcaption className="text-xs text-muted-foreground">Map unavailable: {failure}</figcaption>
      )}
    </figure>
  );
}
