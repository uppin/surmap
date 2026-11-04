import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { SimulationView } from "@/view-model/simulation";

export interface SimulationPaneProps {
  /** The simulation the agent created in this conversation. */
  simulation: SimulationView;
  /** The agent server, against which the scenario's relative URL resolves. */
  serverUrl: string;
  /** The agent's stereo bridge the preview streams its drone's camera to; none: no stream. */
  bridgeUrl?: string;
  /** Called with a bundle the person picked to import into this simulation; no picker without it. */
  onImport?: (bundle: File) => void;
  /** Whether an import is running; the picker is disabled meanwhile. */
  importing?: boolean;
  /** Why the last import was refused; `null` or absent when it was not. */
  importError?: string | null;
}

/**
 * The right-side simulation pane: the created scenario's name and version, its
 * credits, and the scenario's live preview embedded: its `/sim/` page in preview mode (only the
 * camera view — the overview on the ground, the drone's FPV in the air), linked to the fleet so
 * it shows what the agent flies, and streaming to `bridgeUrl` when there is one, so the FPV
 * carries RTAB-Map's keypoints. "Open simulation" opens the full page. The
 * iframe is keyed by id and version, so an agent edit (or an import) that bumps
 * the version reloads the page onto the latest manifest. Export downloads the
 * scenario's bundle; Import hands a picked bundle to `onImport`.
 */
export function SimulationPane(props: SimulationPaneProps): ReactNode {
  const { simulation } = props;
  const src = resolveUrl(props.serverUrl, simulation.url);
  const preview = previewUrl(src, props.bridgeUrl);
  const exportUrl = resolveUrl(props.serverUrl, `/sim/export/${encodeURIComponent(simulation.id)}.zip`);
  const { onImport } = props;
  return (
    <section aria-label="Simulation" className="flex flex-col gap-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Simulation</h2>
        <span className="font-medium">{simulation.name}</span>
        {simulation.version !== null && <Badge variant="secondary">v{simulation.version}</Badge>}
        <div className="ml-auto flex items-center gap-3 text-sm text-muted-foreground">
          <a href={exportUrl} download={`${simulation.id}.surmap-sim.zip`} className="underline underline-offset-2">
            Export
          </a>
          {onImport !== undefined && (
            <label
              className={`underline underline-offset-2 ${props.importing ? "opacity-50" : "cursor-pointer"}`}
            >
              {props.importing ? "Importing…" : "Import"}
              <input
                type="file"
                accept=".zip,application/zip"
                aria-label="Import simulation"
                className="sr-only"
                disabled={props.importing}
                onChange={(event) => {
                  const bundle = event.target.files?.[0];
                  event.target.value = "";
                  if (bundle !== undefined) onImport(bundle);
                }}
              />
            </label>
          )}
          <a href={src} target="_blank" rel="noreferrer" className="underline underline-offset-2">
            Open simulation
          </a>
        </div>
      </div>
      {props.importError && (
        <p role="alert" className="text-sm text-destructive">
          {props.importError}
        </p>
      )}
      <iframe
        key={`${simulation.id}:${simulation.version ?? ""}`}
        title={`Simulation: ${simulation.name}`}
        src={preview}
        className="h-96 w-full rounded-md border bg-muted"
      />
      {simulation.credits.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
          {simulation.credits.map((credit) => (
            <li key={credit}>{credit}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The simulation page at `src` in preview mode, fleet-linked, streaming to `bridgeUrl` if any. */
function previewUrl(src: string, bridgeUrl: string | undefined): string {
  const params = new URLSearchParams({ view: "preview", fleet: "1" });
  if (bridgeUrl) params.set("bridge", bridgeUrl);
  return `${src}${src.includes("?") ? "&" : "?"}${params}`;
}

/** `url` against `serverUrl`; an absolute `url` is used as it is. */
function resolveUrl(serverUrl: string, url: string): string {
  if (/^https?:\/\//.test(url)) return url;
  return `${serverUrl.replace(/\/$/, "")}${url.startsWith("/") ? url : `/${url}`}`;
}
