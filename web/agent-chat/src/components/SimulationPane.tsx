import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { SimulationView } from "@/view-model/simulation";

export interface SimulationPaneProps {
  /** The simulation the agent created in this conversation. */
  simulation: SimulationView;
  /** The agent server, against which the scenario's relative URL resolves. */
  serverUrl: string;
}

/**
 * The right-side simulation pane: the created scenario's name and version, its
 * credits, and the live Bevy simulation page embedded at its `/sim/` URL. The
 * iframe is keyed by id and version, so an agent edit that bumps the version
 * reloads the page onto the latest manifest.
 */
export function SimulationPane(props: SimulationPaneProps): ReactNode {
  const { simulation } = props;
  const src = resolveUrl(props.serverUrl, simulation.url);
  return (
    <section aria-label="Simulation" className="flex flex-col gap-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Simulation</h2>
        <span className="font-medium">{simulation.name}</span>
        {simulation.version !== null && <Badge variant="secondary">v{simulation.version}</Badge>}
        <a
          href={src}
          target="_blank"
          rel="noreferrer"
          className="ml-auto text-sm text-muted-foreground underline underline-offset-2"
        >
          Open simulation
        </a>
      </div>
      <iframe
        key={`${simulation.id}:${simulation.version ?? ""}`}
        title={`Simulation: ${simulation.name}`}
        src={src}
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

/** `url` against `serverUrl`; an absolute `url` is used as it is. */
function resolveUrl(serverUrl: string, url: string): string {
  if (/^https?:\/\//.test(url)) return url;
  return `${serverUrl.replace(/\/$/, "")}${url.startsWith("/") ? url : `/${url}`}`;
}
