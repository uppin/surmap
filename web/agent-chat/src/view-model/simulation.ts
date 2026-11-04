import type { TranscriptItem } from "./transcript";

/** A simulation the agent created in this conversation, as the right-side pane shows it. */
export interface SimulationView {
  id: string;
  name: string;
  /** The scenario version; `null` when the agent only reported the scene's URL. */
  version: number | null;
  /** Where the simulation page opens it, e.g. `/sim/?scenario=downtown-blaze`. */
  url: string;
  credits: string[];
}

const SIMULATION_URL = /\/sim\/\?scenario=([A-Za-z0-9_-]+)/;

/**
 * The simulation this conversation created, or `null` when it created none.
 *
 * A succeeded `create_scenario` tool call is the trigger: its `ScenarioResponse`
 * names the scene. Later succeeded edits returning that same scenario bump the
 * version (and refresh name, URL and credits). Scenes the agent built through a
 * subagent never appear as tool calls here — the subagent's calls stay in its own
 * context — so an assistant reply reporting the `/sim/?scenario=<id>` URL is the
 * fallback signal. Anything else (other tools, failed or running calls, a URL
 * for a scene this conversation did not create after one it did) shows nothing.
 */
export function simulationFromTranscript(items: TranscriptItem[]): SimulationView | null {
  let created: SimulationView | null = null;
  let reported: SimulationView | null = null;
  for (const item of items) {
    if (item.kind === "tool" && item.status === "succeeded") {
      const scenario = scenarioOf(item.resultJson);
      if (scenario === null) continue;
      if (item.tool === "create_scenario") created = scenario;
      else if (created !== null && scenario.id === created.id) created = scenario;
    } else if (item.kind === "assistant") {
      const match = SIMULATION_URL.exec(item.text);
      if (match !== null) {
        const id = match[1];
        reported = { id, name: id, version: null, url: `/sim/?scenario=${id}`, credits: [] };
      }
    }
  }
  return created ?? reported;
}

/** The `scenario` of a tool's `ScenarioResponse` JSON; `null` when it carries none. */
function scenarioOf(resultJson: string | null): SimulationView | null {
  if (resultJson === null) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(resultJson);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const scenario = (parsed as Record<string, unknown>).scenario;
  if (typeof scenario !== "object" || scenario === null) return null;
  const fields = scenario as Record<string, unknown>;
  const id = fields.id;
  if (typeof id !== "string" || id === "") return null;
  const name = fields.name;
  const version = fields.version;
  const url = fields.url;
  const credits = fields.credits;
  return {
    id,
    name: typeof name === "string" && name !== "" ? name : id,
    version: typeof version === "number" ? version : null,
    url: typeof url === "string" && url !== "" ? url : `/sim/?scenario=${id}`,
    credits: Array.isArray(credits)
      ? credits.filter((credit): credit is string => typeof credit === "string")
      : [],
  };
}
