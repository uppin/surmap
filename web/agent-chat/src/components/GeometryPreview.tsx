import { useEffect, useRef, useState, type ReactNode } from "react";

export interface GeometryPreviewProps {
  /** Absolute URL of the object's GLB. */
  url: string;
}

/** A three.js view of an object's GLB (`GLTFLoader`), loaded lazily so the chat bundle stays small. */
export function GeometryPreview(props: GeometryPreviewProps): ReactNode {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let active = true;
    let release: () => void = () => {};
    void import("@/lib/glb-preview")
      .then(({ mountGlbPreview }) => (active ? mountGlbPreview(canvas, props.url) : null))
      .then((stop) => {
        if (stop === null) return;
        if (active) {
          release = stop;
          setReady(true);
        } else {
          stop();
        }
      })
      .catch((error: unknown) => {
        if (active) setFailure(error instanceof Error ? error.message : String(error));
      });
    return () => {
      active = false;
      release();
    };
  }, [props.url]);

  return (
    <figure
      aria-label="Object geometry preview"
      data-geometry-url={props.url}
      className="flex flex-col gap-1 self-stretch"
    >
      {/* Laid out from the start so the renderer can size itself, shown once the model is drawn. */}
      <div className="relative">
        <canvas
          ref={canvasRef}
          className={`block h-64 w-full rounded-md ${ready ? "" : "invisible"}`}
        />
        {!ready && failure === null && (
          <p className="absolute inset-0 grid place-items-center text-xs text-muted-foreground">
            Loading preview…
          </p>
        )}
      </div>
      {failure !== null && (
        <figcaption className="text-xs text-muted-foreground">Preview unavailable: {failure}</figcaption>
      )}
    </figure>
  );
}
